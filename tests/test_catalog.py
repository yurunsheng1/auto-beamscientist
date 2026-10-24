"""Catch duplicate studies and stale/mismatched research artifacts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from build_site import load_papers,build
from verify_site import verify
class CatalogTests(unittest.TestCase):
    def invalid_catalog(self,papers):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'papers.json';path.write_text(json.dumps(papers))
            with self.assertRaises(ValueError):load_papers(path)
    def test_duplicate_id_rejected(self):
        papers=load_papers();self.invalid_catalog(papers+[copy.deepcopy(papers[0])])
    def test_modified_pdf_rejected(self):
        papers=copy.deepcopy(load_papers());papers[0]['sha256']='0'*64;self.invalid_catalog(papers)
    def test_asset_traversal_rejected(self):
        papers=copy.deepcopy(load_papers());papers[0]['pdf']='../README.md';self.invalid_catalog(papers)
    def test_build_all_papers_and_links(self):
        build();verify()
if __name__=='__main__':unittest.main()


class EvidenceTests(unittest.TestCase):
    def test_changed_evidence_fingerprint_is_rejected(self):
        papers=copy.deepcopy(load_papers())
        report=next(p for p in papers if p.get('evidence'))
        report['evidence_sha256']='0'*64
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'papers.json';path.write_text(json.dumps(papers))
            with self.assertRaisesRegex(ValueError,'Evidence archive fingerprint mismatch'):
                load_papers(path)
