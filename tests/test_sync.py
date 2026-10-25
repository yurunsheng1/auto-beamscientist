"""Falsify completion, path, fingerprint and study-identity export gates."""
from pathlib import Path
import base64
import copy
import fcntl
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
    (evidence/'experiment.json').write_text(json.dumps({'schema':'pgcd_manuscript_v1',
        'protocol_alignment':{'faithful':True},'observations':[{'hypothesis':{'id':'H001'},
        'confirmation':{'numerical_valid':True,'robustness_validated':True,
                        'control_checks_passed':True,'resolved_nonnull_effect':True}}]}))
    (directory/'scientific_checks.json').write_text(json.dumps({'version':1,'passed':True,
        'evidence_sha256':hashlib.sha256((evidence/'experiment.json').read_bytes()).hexdigest(),
        'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'tex_sha256':hashlib.sha256((directory/'preprint1.tex').read_bytes()).hexdigest()}))
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
    def test_weak_reject_exports_with_disclosure_and_preserved_verdict(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(exporter.subprocess,'run',side_effect=render):
            source=Path(temp);path,_=fixture(source)
            original={'Decision':'Reject','Soundness':3,'Overall':4}
            reviewfile=path.parent/'automatic_review.json';reviewfile.write_text(json.dumps({'review':original}))
            bundle=exporter.collect(source)
            self.assertEqual(bundle['errors'],[])
            metadata,_,_=sync.validated_entry(bundle['entries'][0])
            self.assertEqual(metadata['review']['decision'],'Reject')
            self.assertEqual(metadata['review']['label'],'Weak reject')
            self.assertIn('revision needed',metadata['limitations'])
            self.assertEqual(json.loads(reviewfile.read_text())['review'],original)
            bad=copy.deepcopy(bundle['entries'][0]);bad['metadata']['review']['label']='Accept'
            with self.assertRaises(ValueError):sync.validated_entry(bad)

    def test_weak_reject_cannot_override_failed_science_or_lower_reviews(self):
        for problem in ('soundness','overall','missing_overall','unconfirmed','changed_pdf'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as temp:
                source=Path(temp);path,_=fixture(source)
                review={'Decision':'Reject','Soundness':3,'Overall':4}
                if problem=='soundness':review['Soundness']=2
                if problem=='overall':review['Overall']=3
                if problem=='missing_overall':review.pop('Overall')
                (path.parent/'automatic_review.json').write_text(json.dumps({'review':review}))
                if problem=='changed_pdf':(path.parent/'preprint1.pdf').write_bytes(b'%PDF-changed')
                if problem=='unconfirmed':
                    p=source/'branch_02/evidence/experiment.json';d=json.loads(p.read_text())
                    d['observations'][0]['confirmation']['numerical_valid']=False;p.write_text(json.dumps(d))
                bundle=exporter.collect(source)
                self.assertEqual(bundle['entries'],[])
                self.assertIn('Publication held',bundle['errors'][0]['error'])

    def test_superseded_weak_reject_is_not_published_as_another_study(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp);fixture(source)
            (source/'branch_02/publication_status.json').write_text('{"status":"superseded"}')
            self.assertEqual(exporter.collect(source)['entries'],[])

    def test_accept_cannot_override_unconfirmed_or_changed_scientific_evidence(self):
        for problem in ('missing_checks','unconfirmed','changed_pdf','changed_tex','changed_evidence','misaligned'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as temp:
                source=Path(temp);path,state=fixture(source)
                evidence=source/'branch_02/evidence/experiment.json'
                if problem=='missing_checks':(path.parent/'scientific_checks.json').unlink()
                elif problem=='changed_pdf':(path.parent/'preprint1.pdf').write_bytes(b'%PDF-Changed after review')
                elif problem=='changed_tex':(path.parent/'preprint1.tex').write_text(r'\title{Changed}\author{A}')
                else:
                    data=json.loads(evidence.read_text())
                    if problem=='unconfirmed':data['observations'][0]['confirmation']['robustness_validated']=False
                    elif problem=='misaligned':data['protocol_alignment']['faithful']=False
                    else:data['question']='Changed after checks'
                    evidence.write_text(json.dumps(data))
                bundle=exporter.collect(source)
                self.assertEqual(bundle['entries'],[])
                self.assertIn('Publication held',bundle['errors'][0]['error'])
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

    def test_shared_repository_lock_prevents_overlapping_publishers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'.git').mkdir()
            with (root/'.git/manuscript-publisher.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with mock.patch.object(sync,'ROOT',root),mock.patch.object(sync,'_sync_once') as action:
                    self.assertEqual(sync.sync_once(Path(temp),'unused',push=True),{'status':'publisher_busy'})
                    action.assert_not_called()

    def test_audited_code_link_survives_sync_only_for_matching_pdf(self):
        for same_pdf in (True, False):
            with self.subTest(same_pdf=same_pdf), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'dist/assets').mkdir(parents=True)
                (root/'data').mkdir()
                metadata = {'id':'pgcd-c1145095930b','sha256':'new-pdf',
                            'pdf':'assets/test.pdf','preview':'assets/test.png'}
                previous = dict(metadata, sha256='new-pdf' if same_pdf else 'old-pdf',
                                code='assets/audited.zip',code_sha256='runtime-hash',summary='old')
                bundle = {'schema':'autobeam-public-artifacts-v1','entries':[{}]}
                with mock.patch.object(sync,'ROOT',root), \
                     mock.patch.object(sync,'load_papers',return_value=[previous]), \
                     mock.patch.object(sync,'validated_entry',return_value=(metadata,b'%PDF',b'PNG')), \
                     mock.patch.object(sync,'build'), mock.patch.object(sync,'verify'):
                    sync.install_bundle(bundle)
                installed = json.loads((root/'data/papers.json').read_text())[0]
                self.assertEqual('code' in installed, same_pdf)
                self.assertEqual('code_sha256' in installed, same_pdf)

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

        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(sync, 'ROOT', Path(temp)), \
             mock.patch.object(sync, 'git', side_effect=fake_git), \
             mock.patch.object(sync, 'bridge_collect', return_value=bundle), \
             mock.patch.object(sync, 'install_bundle', return_value=[]):
            (Path(temp)/'.git').mkdir()
            state = sync.sync_once(Path('/tmp/bridge-fixture'), 'unused', push=True)
        self.assertEqual(state['status'], 'pushed')
        self.assertIn(('push', 'github', 'HEAD:main'), calls)
        self.assertFalse(any(args[0] == 'commit' for args in calls))


if __name__ == '__main__':
    unittest.main()
