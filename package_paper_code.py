"""Build explicitly allowlisted numerical reproduction downloads."""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
PAPERS = ('pgcd-25b0e6a5f760', 'pgcd-2c909e8b5d78')
FILES = ('README.md', 'requirements.txt', 'solver.py', 'reproduce.py',
         'config.json', 'expected.json', 'provenance.json')
IMPORTS = {'argparse', 'csv', 'dataclasses', 'gc', 'json', 'numpy', 'pathlib',
           'platform', 'scipy', 'solver', 'cupy'}


def build_bundle(identity):
    source = ROOT / 'reproducibility' / identity
    files = {name: (source / name).read_bytes() for name in FILES}
    for name, content in files.items():
        if not name.endswith('.py'):
            continue
        for node in ast.walk(ast.parse(content.decode())):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
            if any(module.split('.')[0] not in IMPORTS for module in modules):
                raise ValueError('Unexpected dependency in numerical runtime: ' + name)
    manifest = {'paper_id': identity, 'sha256': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    files['MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    relative = 'assets/' + identity + '-runtime.zip'
    path = ROOT / 'dist' / relative
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return relative, hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    catalog = ROOT / 'data/papers.json'
    papers = json.loads(catalog.read_text())
    for paper in papers:
        if paper['id'] in PAPERS:
            paper['code'], paper['code_sha256'] = build_bundle(paper['id'])
            print(paper['id'], paper['code'], paper['code_sha256'])
    catalog.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
