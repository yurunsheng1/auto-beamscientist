"""Falsify completion, path, fingerprint and study-identity export gates."""
from pathlib import Path
import base64
import copy
import hashlib
import json
import tempfile
import unittest
from unittest import mock

import export_manuscripts as exporter
import sync_manuscripts as sync


def fixture(source, name='manuscript'):
    directory = source / 'branch_02' / name
    directory.mkdir(parents=True)
    pdf = directory / 'preprint1.pdf'
    pdf.write_bytes(b'%PDF-1.5\nunit test fixture, not a research result')
    (directory / 'preprint1.tex').write_text(
        r'\title{A {bounded} numerical test}\author{Auto BeamScientist Project}')
    (directory / 'automatic_review.json').write_text(json.dumps({'review':{'Decision':'Accept','Soundness':3}}))
    (directory / 'automatic_decision.json').write_text(json.dumps({'action':'write_draft','independent_question':True}))
    evidence=source/'branch_02/evidence';evidence.mkdir(exist_ok=True)
    (evidence/'experiment.json').write_text(json.dumps({'schema':'pgcd_manuscript_v1'}))
    state = {'status': 'completed', 'stage': 'finished', 'manuscript': str(pdf),
             'source_run': str(source / 'branch_02/evidence'),
             'updated_at_utc': '2026-10-24T03:16:00+00:00'}
    path = directory / 'paper_pipeline.json'
    path.write_text(json.dumps(state))
    return path, state


def render(command, **kwargs):
    if command[0] == 'pdftotext':
        return mock.Mock(stdout='Title\nAbstract\nThis is an explicitly mocked numerical abstract used only to test artifact transfer.\n1\nIntroduction\n')
    Path(command[-1] + '.png').write_bytes(b'\x89PNG\r\n\x1a\nmock preview')
    return mock.Mock()


class ExportTests(unittest.TestCase):
    def test_delayed_completed_bridge_export_is_consumed_before_new_request(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge = Path(temp)
            identity = 'beam_site_sync_delayed'
            request = {'id': identity, 'command': 'original export request'}
            bundle = {'schema': 'autobeam-public-artifacts-v1', 'entries': []}
            (bridge / 'request.json').write_text(json.dumps(request))
            (bridge / 'response.json').write_text(json.dumps({
                'id': identity, 'status': 'complete',
                'log': exporter.MARKER + json.dumps(bundle)}))
            self.assertEqual(sync.bridge_collect(bridge, 'unused'), bundle)
            self.assertEqual(json.loads((bridge / 'request.json').read_text()), request)
            self.assertEqual((bridge / 'last-consumed-manuscript-export.txt').read_text(), identity)

    def test_withdrawn_branch_never_republishes_completed_manuscripts(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess, 'run', side_effect=render):
            source=Path(temp)
            fixture(source)
            fixture(source,'manuscript_retry')
            (source/'branch_02/publication_status.json').write_text(json.dumps({'status':'withdrawn'}))
            bundle=exporter.collect(source)
            self.assertEqual(bundle['entries'],[])
            self.assertEqual(bundle['withdrawn_ids'],['pgcd-c1145095930b'])

    def test_withdrawal_removes_pdf_preview_citations_and_catalog_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'dist/assets').mkdir(parents=True);(root/'dist/citations').mkdir();(root/'data').mkdir()
            identity='pgcd-c1145095930b'
            paper={'id':identity,'pdf':'assets/'+identity+'.pdf','preview':'assets/'+identity+'.png'}
            names=[paper['pdf'],paper['preview'],'citations/'+identity+'.bib','citations/'+identity+'.html']
            for name in names:(root/'dist'/name).write_bytes(b'old artifact')
            bundle={'schema':'autobeam-public-artifacts-v1','entries':[],'withdrawn_ids':[identity]}
            with mock.patch.object(sync,'ROOT',root),mock.patch.object(sync,'load_papers',return_value=[paper]),mock.patch.object(sync,'build'),mock.patch.object(sync,'verify'):
                changed=sync.install_bundle(bundle)
                self.assertTrue(changed)
                self.assertEqual(json.loads((root/'data/papers.json').read_text()),[])
                self.assertTrue(all(not (root/'dist'/name).exists() for name in names))
            with mock.patch.object(sync,'load_papers',return_value=[]):
                self.assertEqual(sync.install_bundle(bundle),[])

    def test_running_or_unreviewed_pdf_never_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            path, state = fixture(source)
            state['status'] = 'running'
            path.write_text(json.dumps(state))
            self.assertEqual(exporter.collect(source)['entries'], [])
            state['status'] = 'completed'
            path.write_text(json.dumps(state))
            (path.parent / 'automatic_review.json').unlink()
            self.assertEqual(exporter.collect(source)['entries'], [])

    def test_rejected_weak_duplicate_or_audit_documents_are_held(self):
        for problem in ('rejected','weak','duplicate','audit'):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as temp:
                source=Path(temp);path,state=fixture(source)
                if problem in ('rejected','weak'):
                    review={'Decision':'Reject' if problem=='rejected' else 'Accept','Soundness':2 if problem=='weak' else 3}
                    (path.parent/'automatic_review.json').write_text(json.dumps({'review':review}))
                elif problem=='duplicate':
                    (path.parent/'automatic_decision.json').write_text(json.dumps({'action':'write_draft','independent_question':False}))
                else:
                    (source/'branch_02/evidence/experiment.json').write_text('{"schema":"numerical_audit"}')
                bundle=exporter.collect(source)
                self.assertEqual(bundle['entries'],[])
                self.assertIn('Publication held',bundle['errors'][0]['error'])

    def test_completed_export_contains_only_public_artifacts_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess, 'run', side_effect=render):
            source = Path(temp)
            fixture(source)
            fixture(source, 'manuscript_retry')
            bundle = exporter.collect(source)
            self.assertEqual(bundle['errors'], [])
            self.assertEqual(len(bundle['entries']), 1)
            entry = bundle['entries'][0]
            metadata, pdf, preview = sync.validated_entry(entry)
            self.assertEqual(metadata['title'], 'A {bounded} numerical test')
            self.assertEqual(metadata['authors'], 'Auto BeamScientist Project')
            self.assertEqual(metadata['provenance']['study'], 'branch_02/evidence')
            self.assertNotIn(str(source), json.dumps(bundle))
            catalog = [metadata]
            with mock.patch.object(sync, 'load_papers', return_value=catalog):
                self.assertEqual(sync.install_bundle(bundle), [])

    def test_escaping_completed_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            path, state = fixture(source)
            state['manuscript'] = str(source / 'secret.pdf')
            path.write_text(json.dumps(state))
            bundle = exporter.collect(source)
            self.assertEqual(bundle['entries'], [])
            self.assertIn('escapes', bundle['errors'][0]['error'])

    def test_editorial_revision_retains_original_writer_and_completion_date(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess, 'run', side_effect=render):
            source = Path(temp)
            path, state = fixture(source)
            state['editorial_revision'] = {
                'editor': 'Codex', 'original_completed_at_utc': '2026-10-24T03:16:00+00:00',
                'revised_at_utc': '2026-10-24T03:57:00+00:00'}
            state['updated_at_utc'] = state['editorial_revision']['revised_at_utc']
            path.write_text(json.dumps(state))
            metadata = exporter.collect(source)['entries'][0]['metadata']
            self.assertEqual(metadata['provenance']['writer'], 'AI Scientist-v2')
            self.assertEqual(metadata['provenance']['editor'], 'Codex')
            self.assertEqual(metadata['provenance']['completed_at_utc'], '2026-10-24T03:16:00+00:00')
            self.assertEqual(metadata['provenance']['revised_at_utc'], '2026-10-24T03:57:00+00:00')

    def test_system_batches_export_completed_manuscripts(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess,'run',side_effect=render):
            source=Path(temp);batch=source/'batch_0001';batch.mkdir()
            fixture(batch)
            bundle=exporter.collect(source)
            self.assertEqual(bundle['errors'],[])
            self.assertEqual(len(bundle['entries']),1)
            self.assertEqual(bundle['entries'][0]['metadata']['provenance']['study'],'batch_0001/branch_02/evidence')

    def test_received_tampering_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess, 'run', side_effect=render):
            source = Path(temp)
            fixture(source)
            entry = exporter.collect(source)['entries'][0]
        for field, value in [('sha256', '0' * 64), ('pdf', '../private.pdf')]:
            bad = copy.deepcopy(entry)
            bad['metadata'][field] = value
            with self.assertRaises(ValueError):
                sync.validated_entry(bad)
        bad = copy.deepcopy(entry)
        bad['completed'] = False
        with self.assertRaises(ValueError):
            sync.validated_entry(bad)

    def test_failed_push_is_retried_without_duplicate_commits(self):
        bundle = {'schema': 'autobeam-public-artifacts-v1', 'entries': [],
                  'research_status': 'running', 'research_stage': 'writeup'}
        calls = []

        def fake_git(*args):
            calls.append(args)
            if args[0] == 'remote':
                return sync.EXPECTED_REMOTE
            if args[0] == 'branch':
                return 'main'
            if args[0] == 'rev-list':
                return '1'
            return ''

        with mock.patch.object(sync, 'git', side_effect=fake_git), \
             mock.patch.object(sync, 'bridge_collect', return_value=bundle), \
             mock.patch.object(sync, 'install_bundle', return_value=[]):
            state = sync.sync_once(Path('/tmp/bridge-fixture'), 'unused', push=True)
        self.assertEqual(state['status'], 'pushed')
        self.assertIn(('push', 'github', 'HEAD:main'), calls)
        self.assertFalse(any(args[0] == 'commit' for args in calls))


if __name__ == '__main__':
    unittest.main()
