"""Export completed AI Scientist manuscripts as public-only website artifacts.

Run on the research host. No credentials, model transcripts, or numerical source
code are included. A compiled intermediate PDF is never sufficient for export.
"""
from pathlib import Path
import argparse
import base64
import datetime
import hashlib
import json
import re
import subprocess
import tempfile

MARKER = 'AUTOBEAM_MANUSCRIPTS='
MAX_PDF_BYTES = 15 * 1024 * 1024


def study_id(study, source):
    marker = Path(source) / 'publication_namespace.json'
    identity = study
    if marker.exists():
        namespace = json.loads(marker.read_text()).get('namespace')
        if not isinstance(namespace, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', namespace):
            raise ValueError('Invalid publication namespace')
        identity = namespace + '/' + study
    return 'pgcd-' + hashlib.sha256(identity.encode()).hexdigest()[:12]


def review_clearance(review):
    """User permits weak rejects as labelled preprints; scientific gates remain."""
    soundness=review.get('Soundness');overall=review.get('Overall');decision=review.get('Decision')
    if type(soundness) not in (int,float) or not 3<=soundness<=4:
        raise ValueError('Publication held: scientific soundness must be at least 3/4')
    weak=(decision=='Reject' and type(overall) in (int,float) and 4<=overall<=5)
    if decision!='Accept' and not weak:
        raise ValueError('Publication held: review is below the authorized weak-reject threshold')
    return {'decision':decision,'label':'Weak reject' if weak else 'Accept',
            'overall':overall,'soundness':soundness,'kind':'AI review',
            'status':'Revision needed' if weak else 'AI recommended for sharing'}


def contained(path, root):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Artifact escapes the research directory')
    return path


def tex_group(text, command):
    match = re.search(r'\\' + command + r'(?:\[[^\]]*\])?\s*\{', text)
    if not match:
        raise ValueError('Manuscript is missing ' + command)
    depth = 1
    start = match.end()
    for i in range(start, len(text)):
        if text[i] in '{}' and (i == 0 or text[i - 1] != '\\'):
            depth += 1 if text[i] == '{' else -1
            if depth == 0:
                return text[start:i]
    raise ValueError('Unclosed manuscript metadata')


def plain_tex(text):
    text = re.sub(r'\\(?:label|cite\w*)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:textbf|textit|textrm|mathrm|emph)\{([^{}]*)\}', r'\1', text)
    text = re.sub(r'\\([%&_#])', r'\1', text).replace('~', ' ')
    text = re.sub(r'\\\\(?:\[[^\]]*\])?', ' ', text)
    # Keep mathematical content; metadata is escaped by the HTML builder.
    return ' '.join(text.split()).strip()


def export_one(statefile, source):
    statefile = contained(statefile, source)
    state = json.loads(statefile.read_text())
    if state.get('status') != 'completed' or state.get('stage') != 'finished':
        return None
    directory = statefile.parent
    publication = directory.parent / 'publication_status.json'
    if publication.exists() and json.loads(publication.read_text()).get('status') in ('withdrawn','superseded'):
        return None
    reviewfile=directory/'automatic_review.json'
    decisionfile=directory/'automatic_decision.json'
    if not reviewfile.is_file() or not decisionfile.is_file():
        return None
    review=json.loads(reviewfile.read_text()).get('review',{})
    decision=json.loads(decisionfile.read_text())
    # Weak rejects may be shared with their actual verdict. Numerical failures
    # and duplicate studies still cannot pass through manuscript scoring.
    if decision.get('action')!='write_draft' or decision.get('independent_question') is not True:
        raise ValueError('Publication held: the research manager did not establish a distinct manuscript question')
    clearance=review_clearance(review)
    evidence=contained(Path(state['source_run']),source)
    evidencefile=evidence/'experiment.json'
    if not evidencefile.is_file() or json.loads(evidencefile.read_text()).get('schema')!='pgcd_manuscript_v1':
        raise ValueError('Publication held: artifact is not a research manuscript with scientific evidence')
    packet=json.loads(evidencefile.read_text())
    checksfile=directory/'scientific_checks.json'
    if not checksfile.is_file():
        raise ValueError('Publication held: deterministic scientific checks are missing')
    checks=json.loads(checksfile.read_text())
    if checks.get('passed') is not True or checks.get('version')!=1:
        raise ValueError('Publication held: scientific checks did not pass')
    if packet.get('protocol_alignment',{}).get('faithful') is not True:
        raise ValueError('Publication held: research question and executed protocol are not aligned')
    confirmed=[]
    for record in packet.get('observations',[]):
        confirmation=record.get('confirmation',{})
        if all(confirmation.get(k) is True for k in ('numerical_valid','robustness_validated','control_checks_passed','resolved_nonnull_effect')):
            confirmed.append(record['hypothesis']['id'])
    if not confirmed:
        raise ValueError('Publication held: no independently confirmed nonnull observations with valid controls')
    if checks.get('evidence_sha256')!=hashlib.sha256(evidencefile.read_bytes()).hexdigest():
        raise ValueError('Publication held: scientific evidence changed after checks')
    pdf = contained(Path(state['manuscript']), directory)
    if not pdf.is_file() or not 10 < pdf.stat().st_size <= MAX_PDF_BYTES:
        raise ValueError('Missing or oversized completed manuscript')
    content = pdf.read_bytes()
    if not content.startswith(b'%PDF-'):
        raise ValueError('Completed artifact is not a PDF')
    tex = contained(directory / 'preprint1.tex', directory).read_text()
    if (checks.get('pdf_sha256')!=hashlib.sha256(content).hexdigest() or
        checks.get('tex_sha256')!=hashlib.sha256((directory/'preprint1.tex').read_bytes()).hexdigest()):
        raise ValueError('Publication held: manuscript changed after scientific checks')
    title = plain_tex(tex_group(tex, 'title'))
    author = plain_tex(tex_group(tex, 'author'))
    if not title or not author:
        raise ValueError('Empty manuscript title or author')
    # Read the actual compiled abstract instead of inventing a promotional one.
    result = subprocess.run(['pdftotext', str(pdf), '-'], capture_output=True,
                            text=True, check=True, timeout=30)
    match = re.search(r'\bAbstract\s*\n(.*?)(?:\n\s*1\s*\n\s*Introduction\b|\n\s*1\s+Introduction\b|\n\s*Introduction\b)',
                      result.stdout, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError('Could not identify the compiled abstract')
    abstract = ' '.join(match.group(1).split())
    if not 40 <= len(abstract) <= 10000:
        raise ValueError('Unexpected abstract size')
    # The evidence source is stable across manuscript retries and revisions.
    evidence = contained(Path(state['source_run']), source)
    study = str(evidence.relative_to(source))
    paper_id = study_id(study, source)
    with tempfile.TemporaryDirectory(prefix='beam-preview-') as temp:
        prefix = Path(temp) / 'first-page'
        subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1100',
                        '-png', str(pdf), str(prefix)], capture_output=True,
                       check=True, timeout=45)
        preview = prefix.with_suffix('.png').read_bytes()
    year = datetime.datetime.fromisoformat(state['updated_at_utc']).year
    metadata = {
        'id': paper_id, 'title': title, 'authors': author, 'year': year,
        'topic': 'Computational photonics', 'status': 'Research report',
        'pdf': 'assets/' + paper_id + '.pdf',
        'preview': 'assets/' + paper_id + '.png',
        'summary': abstract.split('. ')[0] + ('' if abstract.split('. ')[0].endswith('.') else '.'),
        'abstract': abstract,
        'limitations': ('AI review: Weak reject; revision needed. ' if clearance['decision']=='Reject' else '')+'Numerical simulation study; see the manuscript for scope and unresolved tests.',
        'review':clearance,
        'sha256': hashlib.sha256(content).hexdigest(),
        'provenance': {'study': study, 'writer': 'AI Scientist-v2',
                       'completed_at_utc': state['updated_at_utc']},
    }
    editorial = state.get('editorial_revision')
    if editorial:
        metadata['provenance']['completed_at_utc'] = editorial['original_completed_at_utc']
        metadata['provenance']['editor'] = editorial['editor']
        metadata['provenance']['revised_at_utc'] = editorial['revised_at_utc']
    return {'completed': True, 'metadata': metadata,
            'pdf_base64': base64.b64encode(content).decode(),
            'preview_base64': base64.b64encode(preview).decode()}


def collect(source):
    source = Path(source).resolve()
    entries, errors = {}, []
    # A later completed revision replaces the same study, never adds a new paper.
    states = sorted([*source.glob('branch_*/manuscript*/paper_pipeline.json'),*source.glob('batch_*/branch_*/manuscript*/paper_pipeline.json')],
                    key=lambda p: p.stat().st_mtime)
    for statefile in states:
        try:
            item = export_one(statefile, source)
            if item:
                entries[item['metadata']['id']] = item
        except Exception as exc:
            errors.append({'artifact': str(statefile.relative_to(source)),
                           'error': str(exc), 'error_type': type(exc).__name__})
    withdrawn=[]
    for branch in sorted([*source.glob('branch_*'),*source.glob('batch_*/branch_*')]):
        marker=branch/'publication_status.json'
        if marker.exists() and json.loads(marker.read_text()).get('status') in ('withdrawn','superseded'):
            study=str((branch/'evidence').relative_to(source))
            withdrawn.append(study_id(study, source))
    pipeline = source / 'pipeline_state.json'
    state = json.loads(pipeline.read_text()) if pipeline.exists() else {}
    return {'schema': 'autobeam-public-artifacts-v1', 'entries': list(entries.values()),
            'errors': errors, 'withdrawn_ids': withdrawn, 'research_status': state.get('status', 'unknown'),
            'research_stage': state.get('stage', 'unknown'),
            'exported_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    print(MARKER + json.dumps(collect(args.source), ensure_ascii=False))
