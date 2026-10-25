"""Falsify accidental timestamp inheritance and inconsistent evidence receipts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from build_site import load_papers,publication_html
from publication_records import read_records,verified_versions
from unittest import mock
import publication_records as pr
class PublicationTests(unittest.TestCase):
    def test_modified_pdf_never_inherits_current_version_timestamp(self):
        paper=copy.deepcopy(load_papers()[0]);records=read_records()
        self.assertIsNotNone(verified_versions(paper,records)[1])
        paper['sha256']='0'*64
        self.assertIsNone(verified_versions(paper,records)[1])
        self.assertIn('Verification pending for this PDF version',publication_html(paper,records)[1])
    def test_timestamp_must_match_server_receipt(self):
        records=copy.deepcopy(read_records())
        first=next(iter(records['papers'].values()))['versions'][0]
        first['published_at_utc']='2020-01-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'records.json';p.write_text(json.dumps(records))
            with self.assertRaises(ValueError):read_records(p)
    def test_first_release_stays_separate_from_revision(self):
        paper=next(p for p in load_papers() if p['id']=='core-energy-concentration')
        first,current=verified_versions(paper,read_records())
        self.assertLess(first['published_at_utc'],current['published_at_utc'])
        self.assertNotEqual(first['pdf_sha256'],current['pdf_sha256'])
    def test_failed_deployment_never_becomes_publication_evidence(self):
        paper=load_papers()[0]
        deploy={'id':123,'sha':'a'*40,'created_at':'2026-10-25T01:00:00Z'}
        pdf=(Path(__file__).resolve().parents[1]/'dist'/paper['pdf']).read_bytes()
        def fake_api(path,paginate=False):
            return [{'state':'failure','created_at':'2026-10-25T01:01:00Z'}] if '/statuses' in path else [deploy]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'data/papers.json').write_text(json.dumps([paper]))
            with mock.patch.object(pr,'ROOT',root),mock.patch.object(pr,'RECORDS',root/'data/publication-records.json'),mock.patch.object(pr,'api',side_effect=fake_api),mock.patch.object(pr,'git_file',side_effect=lambda commit,path: json.dumps([paper]).encode() if path=='data/papers.json' else pdf):
                pr.refresh()
                self.assertEqual(pr.verified_versions(paper,pr.read_records()),(None,None))
