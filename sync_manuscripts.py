"""Synchronize completed GPU manuscripts to this GitHub Pages repository.

Uses the already connected 4090hk VS Code file bridge and this Mac's existing
GitHub Git credentials. No GitHub or model credentials are copied to the GPU.
"""
from pathlib import Path
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import uuid

from build_site import build, load_papers
from verify_site import verify
from export_manuscripts import MARKER, MAX_PDF_BYTES, collect

ROOT = Path(__file__).resolve().parent
REMOTE = '/home/nvidia/Documents/yrs/AutoPhotonics_AI_Scientist_Codex'
EXPECTED_REMOTE = 'https://github.com/yurunsheng1/auto-beamscientist.git'


def log(message):
    print(datetime.datetime.now(datetime.timezone.utc).isoformat(), message, flush=True)


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, text=True,
                            capture_output=True, timeout=90,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
    if result.returncode:
        raise RuntimeError('Git ' + args[0] + ' failed: ' + result.stderr.strip())
    return result.stdout.strip()


def bridge_collect(bridge, remote_source, timeout=100):
    bridge = Path(bridge)
    lock = (bridge / '.manuscript-sync.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    try:
        request, response = bridge / 'request.json', bridge / 'response.json'
        consumed = bridge / 'last-consumed-manuscript-export.txt'
        def read_bundle(result):
            for line in result.get('log', '').splitlines():
                if line.startswith(MARKER):
                    bundle = json.loads(line[len(MARKER):])
                    consumed.write_text(result['id'])
                    return bundle
            return None
        if request.exists() and response.exists():
            q, r = json.loads(request.read_text()), json.loads(response.read_text())
            if r.get('id') != q.get('id') or r.get('status') == 'running':
                log('Bridge busy; leaving the existing request untouched')
                return None
            if (r.get('status') == 'complete' and r.get('id', '').startswith('beam_site_sync_')
                    and (not consumed.exists() or consumed.read_text() != r['id'])):
                # Slow tunnel reads can finish after our timeout. Consume that
                # completed export before issuing another request.
                bundle = read_bundle(r)
                if bundle is not None:
                    return bundle
        identity = 'beam_site_sync_' + uuid.uuid4().hex
        command = ' '.join(shlex.quote(p) for p in [
            REMOTE + '/.venv/bin/python',
            REMOTE + '/websites/auto-beamscientist/export_manuscripts.py',
            '--source', remote_source])
        pending = request.with_suffix('.pending')
        pending.write_text(json.dumps({'id': identity, 'command': command}))
        pending.replace(request)
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            time.sleep(2)
            if not response.exists():
                continue
            try:
                result = json.loads(response.read_text())
            except json.JSONDecodeError:
                continue
            if result.get('id') != identity:
                continue
            output = result.get('log', '')
            bundle = read_bundle(result)
            if bundle is not None:
                return bundle
            if result.get('status') in ('failed', 'complete'):
                raise RuntimeError('Remote artifact export failed: ' +
                                   result.get('error', output[-2000:]))
        raise TimeoutError('Waiting for the connected 4090hk VS Code bridge')
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def validated_entry(item):
    if item.get('completed') is not True:
        raise ValueError('Only completed manuscripts may be published')
    metadata = item['metadata']
    paper_id = metadata['id']
    if not re.fullmatch(r'pgcd-[0-9a-f]{12}', paper_id):
        raise ValueError('Unexpected manuscript identifier')
    for name in ('title', 'authors', 'topic', 'summary', 'abstract', 'limitations'):
        if not isinstance(metadata[name], str) or not 1 <= len(metadata[name]) <= 10000:
            raise ValueError('Invalid public manuscript metadata')
    if metadata['status'] != 'Research report' or not 2020 <= metadata['year'] <= 2100:
        raise ValueError('Invalid manuscript status or year')
    pdf = base64.b64decode(item['pdf_base64'], validate=True)
    preview = base64.b64decode(item['preview_base64'], validate=True)
    if not 10 < len(pdf) <= MAX_PDF_BYTES or not pdf.startswith(b'%PDF-'):
        raise ValueError('Invalid PDF')
    if hashlib.sha256(pdf).hexdigest() != metadata['sha256']:
        raise ValueError('PDF fingerprint mismatch')
    if not preview.startswith(b'\x89PNG\r\n\x1a\n') or len(preview) > 10 * 1024 * 1024:
        raise ValueError('Invalid preview image')
    if metadata['pdf'] != 'assets/' + paper_id + '.pdf' or metadata['preview'] != 'assets/' + paper_id + '.png':
        raise ValueError('Unsafe asset path')
    allowed = {'id', 'title', 'authors', 'year', 'topic', 'status', 'pdf', 'preview',
               'summary', 'abstract', 'limitations', 'sha256', 'provenance'}
    if set(metadata) - allowed:
        raise ValueError('Unexpected public metadata fields')
    return metadata, pdf, preview


def install_bundle(bundle):
    if bundle.get('schema') != 'autobeam-public-artifacts-v1':
        raise ValueError('Unexpected artifact bundle schema')
    # Validate every entry before making any changes.
    entries = [validated_entry(e) for e in bundle['entries']]
    withdrawn=bundle.get('withdrawn_ids',[])
    if not isinstance(withdrawn,list) or any(not isinstance(i,str) or not re.fullmatch(r'pgcd-[0-9a-f]{12}',i) for i in withdrawn):
        raise ValueError('Invalid withdrawn study identifiers')
    if set(withdrawn)&{metadata['id'] for metadata,_,_ in entries}:
        raise ValueError('The same study cannot be published and withdrawn')
    papers = load_papers()
    by_id = {p['id']: p for p in papers}
    changed = []
    for identity in withdrawn:
        previous=by_id.pop(identity,None)
        if previous is None:continue
        for name in [previous['pdf'],previous['preview'],'citations/'+identity+'.bib','citations/'+identity+'.html']:
            asset=ROOT/'dist'/name
            if not asset.resolve().is_relative_to((ROOT/'dist').resolve()):
                raise ValueError('Unsafe withdrawn artifact path')
            if asset.is_file():
                asset.unlink();changed.append(str(asset.relative_to(ROOT)))
        changed.append('data/papers.json')
    for metadata, pdf, preview in entries:
        if by_id.get(metadata['id']) == metadata:
            continue
        for key, content in [('pdf', pdf), ('preview', preview)]:
            asset = ROOT / 'dist' / metadata[key]
            temporary = asset.with_suffix(asset.suffix + '.pending')
            temporary.write_bytes(content)
            temporary.replace(asset)
            changed.append(str(asset.relative_to(ROOT)))
        by_id[metadata['id']] = metadata
    if changed:
        catalog = ROOT / 'data/papers.json'
        catalog.write_text(json.dumps(list(by_id.values()), ensure_ascii=False, indent=2) + '\n')
        build()
        verify()
        changed += ['data/papers.json', 'dist/index.html']
        for metadata, _, _ in entries:
            for suffix in ('.bib', '.html'):
                citation = ROOT / 'dist/citations' / (metadata['id'] + suffix)
                if citation.is_file():
                    changed.append(str(citation.relative_to(ROOT)))
    return changed


def sync_once(bridge, remote_source, *, push, local=False, remote="github"):
    if git('remote', 'get-url', remote) != EXPECTED_REMOTE:
        raise RuntimeError('Refusing to publish to a different repository')
    if git('branch', '--show-current') != 'main':
        raise RuntimeError('Website repository must be on main')
    if git('status', '--porcelain'):
        raise RuntimeError('Website has uncommitted edits; leaving them untouched')
    # Fast-forward only; a website edit must never be overwritten by automation.
    git('pull', '--ff-only', remote, 'main')
    bundle = collect(Path(remote_source)) if local else bridge_collect(bridge, remote_source)
    if bundle is None:
        return {'status': 'bridge_busy'}
    if bundle.get('errors'):
        log('Exporter diagnostics: ' + json.dumps(bundle['errors']))
    changed = install_bundle(bundle)
    if changed:
        subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                       cwd=ROOT, check=True, timeout=90)
        git('add', '--', *changed)
        git('commit', '-m', 'Publish completed Auto BeamScientist research manuscripts')
    ahead = int(git('rev-list', '--count', remote+'/main..HEAD'))
    if push and ahead:
        # Retrying a failed push also works when no new manuscript arrived.
        git('push', remote, 'HEAD:main')
        log('Pushed manuscripts to GitHub Pages: ' + git('rev-parse', '--short', 'HEAD'))
    return {'status': 'pushed' if push and ahead else 'no_new_manuscripts',
            'changed': changed, 'research_status': bundle.get('research_status'),
            'research_stage': bundle.get('research_stage'),
            'completed_exports': len(bundle['entries']),
            'export_errors': bundle.get('errors', []), 'commit': git('rev-parse', 'HEAD')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', type=Path, default=Path('/tmp/codex-remote-setup'))
    parser.add_argument('--source', default=REMOTE + '/runs/pgcd/deepening/autonomous')
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--local', action='store_true', help='Read completed manuscripts from the local research system')
    parser.add_argument('--remote', default='github', help='Existing Git remote for the authorized website')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--push', action='store_true', help='User-authorized GitHub Pages publishing')
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--max-hours', type=float, default=8)
    args = parser.parse_args()
    if args.interval < 15 or not 0 < args.max_hours <= 24:
        parser.error('Use interval >=15 seconds and max-hours in (0,24]')
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = (args.state_dir / 'publisher.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (args.state_dir / 'publisher.pid').write_text(str(os.getpid()))
    deadline = time.monotonic() + args.max_hours * 3600
    while True:
        if (args.state_dir / 'STOP').exists():
            log('Publisher stopped by STOP file')
            break
        try:
            state = sync_once(args.bridge, args.source, push=args.push, local=args.local, remote=args.remote)
        except Exception as exc:
            state = {'status': 'retrying', 'error': str(exc), 'error_type': type(exc).__name__}
        state['checked_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.state_dir / 'publisher_state.json').write_text(json.dumps(state, indent=2))
        log(json.dumps(state))
        if not args.watch or time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval, max(0, deadline - time.monotonic())))


if __name__ == '__main__':
    main()
