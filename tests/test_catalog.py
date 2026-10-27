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
    def test_review_scores_are_omitted_from_cards_and_citation(self):
        from unittest import mock
        from build_site import bibtex
        paper=copy.deepcopy(load_papers()[0])
        paper['review']={'decision':'Reject','label':'Weak reject','overall':4,'soundness':3,'kind':'AI review','status':'Revision needed'}
        with mock.patch('build_site.load_papers',return_value=[paper]):
            build()
            text=(Path(__file__).resolve().parents[1]/'dist/index.html').read_text()
            self.assertNotIn('AI review: Weak reject',text)
            self.assertNotIn('Soundness 3/4',text)
            self.assertNotIn('Revision needed',text)
        self.assertNotIn('reject',bibtex(paper).lower())
        build()
if __name__=='__main__':unittest.main()
