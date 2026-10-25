"""Audit the public numerical packages against their explicit file allowlist."""
import ast
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from package_paper_code import FILES, IMPORTS, PAPERS, ROOT


class CodeBundleTests(unittest.TestCase):
    def test_only_allowlisted_numerical_sources_are_downloadable(self):
        catalog = json.loads((ROOT/'data/papers.json').read_text())
        papers = {paper['id']:paper for paper in catalog}
        for identity in PAPERS:
            with self.subTest(paper=identity):
                path = ROOT/'dist'/papers[identity]['code']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),papers[identity]['code_sha256'])
                with zipfile.ZipFile(path) as bundle:
                    self.assertEqual(set(bundle.namelist()),set(FILES)|{'MANIFEST.json'})
                    manifest = json.loads(bundle.read('MANIFEST.json'))
                    self.assertEqual(manifest['paper_id'],identity)
                    for name in FILES:
                        content = bundle.read(name)
                        self.assertEqual(hashlib.sha256(content).hexdigest(),manifest['sha256'][name])
                        self.assertEqual(content,(ROOT/'reproducibility'/identity/name).read_bytes())
                        if name.endswith('.py'):
                            for node in ast.walk(ast.parse(content.decode())):
                                modules = [a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
                                self.assertTrue(all(module.split('.')[0] in IMPORTS for module in modules))


if __name__ == '__main__':
    unittest.main()
