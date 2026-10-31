# -*- coding: utf-8 -*-
"""Review/API regression tests with temporary storage and a fake detector.

Run: python scripts/test_review_workflow.py
No model weights, cloud credentials, or network calls are needed.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import quote

DEV = Path(__file__).resolve().parents[1]
IMPORT_STORAGE = tempfile.TemporaryDirectory(prefix='steelscan_review_import_')
os.environ['STEELSCAN_STORAGE_DIR'] = IMPORT_STORAGE.name
os.environ['STEELSCAN_DB'] = str(Path(IMPORT_STORAGE.name) / 'test.db')
os.environ['DEEPSEEK_API_KEY'] = ''
sys.path.insert(0, str(DEV))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api_v1  # noqa: E402
import config  # noqa: E402
import llm  # noqa: E402
import runtime  # noqa: E402
import storage  # noqa: E402
from server import app  # noqa: E402


class FakeDetector:
    def detect(self, image, **kwargs):
        defects = [
            {'class_id': 2, 'class_name': 'patches', 'class_cn': '斑块',
             'confidence': 0.9, 'bbox_xyxy': [20, 20, 70, 80], 'area_ratio': 0.075},
            {'class_id': 2, 'class_name': 'patches', 'class_cn': '斑块',
             'confidence': 0.8, 'bbox_xyxy': [80, 80, 110, 110], 'area_ratio': 0.0225},
            {'class_id': 0, 'class_name': 'crazing', 'class_cn': '龟裂',
             'confidence': 0.7, 'bbox_xyxy': [120, 110, 160, 180], 'area_ratio': 0.07},
        ]
        return {'width': image.shape[1], 'height': image.shape[0],
                'defects': defects, 'defect_count': len(defects),
                'inference_ms': 1.25, 'model': 'yolo26n-640-onnx', 'imgsz': 640}


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='steelscan_review_')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for target, values in (
            (storage, {'STORAGE_DIR': str(root), 'IMAGES_DIR': str(root / 'images'),
                       'DB_PATH': str(root / 'test.db')}),
            (config, {'API_KEY': ''}),
        ):
            patcher = patch.multiple(target, **values)
            patcher.start()
            self.addCleanup(patcher.stop)
        detector_patch = patch.object(runtime, 'get_detector', return_value=FakeDetector())
        detector_patch.start()
        self.addCleanup(detector_patch.stop)
        llm_patch = patch.object(llm, 'available', return_value=False)
        llm_patch.start()
        self.addCleanup(llm_patch.stop)
        storage.init_db()
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        ok, encoded = cv2.imencode('.png', np.full((200, 200, 3), 128, dtype=np.uint8))
        self.assertTrue(ok)
        self.image = encoded.tobytes()

    def upload(self, batch='BATCH-A'):
        response = self.client.post('/api/inspections',
                                    files={'image': ('sample.png', self.image, 'image/png')},
                                    data={'batch_no': batch, 'workpiece_no': 'W-1'})
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertEqual(created['status'], 'completed')
        self.assertEqual(created['model_version'], 'yolo26n-640-onnx')
        return self.detail(created['inspection_id'])

    def detail(self, inspection_id):
        response = self.client.get('/api/inspections/' + inspection_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def review(self, inspection_id, version, **values):
        payload = {'base_version': version, 'review_status': 'corrected', **values}
        return self.client.post('/api/inspections/' + inspection_id + '/review', json=payload)

    def assert_empty_storage(self):
        with storage.get_conn() as conn:
            for table in ('inspections', 'detections', 'tasks'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual(list(Path(storage.IMAGES_DIR).iterdir()), [])

    def test_complete_diff_preserves_predictions_and_stable_manual_ids(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        original = copy.deepcopy(detail['detections'])
        self.assertEqual(detail['review_version'], 0)
        self.assertIsNone(detail['analysis'])
        for name in ('original_url', 'annotated_url'):
            self.assertEqual(self.client.get(detail[name]).status_code, 200)
        manual_id = str(uuid4())
        corrections = [
            {'op': 'update', 'detection_id': original[0]['detection_id'],
             'class_id': 1, 'bbox_xyxy': [10, 15, 65, 75]},
            {'op': 'delete', 'detection_id': original[1]['detection_id']},
            {'op': 'add', 'detection_id': manual_id, 'class_id': 5,
             'bbox_xyxy': [150, 10, 180, 90]},
        ]
        response = self.review(inspection_id, 0, corrections=corrections)
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.detail(inspection_id)
        self.assertEqual(detail['detections'], original)
        self.assertEqual(detail['review_version'], 1)
        effective = {d['detection_id']: d for d in detail['reviewed_detections']}
        self.assertEqual(set(effective), {original[0]['detection_id'], original[2]['detection_id'], manual_id})
        self.assertEqual(effective[original[0]['detection_id']]['class_name'], 'inclusion')
        for detection_id in (original[0]['detection_id'], manual_id):
            self.assertEqual(effective[detection_id]['source'], 'manual')
            self.assertIsNone(effective[detection_id]['score'])
        self.assertEqual(effective[original[2]['detection_id']]['source'], 'model')
        self.assertEqual(effective[original[2]['detection_id']]['score'], original[2]['score'])

        # The second save is a full diff: omitted original operations are undone.
        manual = {**corrections[2], 'bbox_xyxy': [140, 20, 180, 100]}
        response = self.review(inspection_id, 1, corrections=[manual])
        self.assertEqual(response.status_code, 200, response.text)
        effective = self.detail(inspection_id)['reviewed_detections']
        self.assertEqual(len(effective), 4)
        self.assertEqual(next(d for d in effective if d['detection_id'] == manual_id)['bbox_xyxy'],
                         manual['bbox_xyxy'])
        self.assertEqual(next(d for d in effective if d['detection_id'] == original[0]['detection_id'])['source'],
                         'model')
        response = self.review(inspection_id, 2, corrections=[])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.detail(inspection_id)['reviewed_detections']), 3)

    def test_legacy_update_null_preservation_and_explicit_reset(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        original = detail['detections']
        response = self.review(inspection_id, 0, corrections=[
            {'detection_id': original[0]['detection_id'], 'class_id': 5},
        ])
        self.assertEqual(response.status_code, 200, response.text)
        corrected = self.detail(inspection_id)['reviewed_detections']
        changed = next(d for d in corrected if d['detection_id'] == original[0]['detection_id'])
        self.assertEqual(changed['class_id'], 5)
        self.assertEqual(changed['bbox_xyxy'], original[0]['bbox_xyxy'])
        for version, values in ((1, {'corrections': None}), (2, {})):
            response = self.review(inspection_id, version, notes='keep saved edits', **values)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.detail(inspection_id)['reviewed_detections'], corrected)
        response = self.review(inspection_id, 3, corrections=[])
        self.assertEqual(response.status_code, 200, response.text)
        restored = self.detail(inspection_id)
        self.assertEqual(restored['detections'], original)
        self.assertTrue(all(d['source'] == 'model' for d in restored['reviewed_detections']))
        self.assertEqual([d['class_id'] for d in restored['reviewed_detections']],
                         [d['class_id'] for d in original])

    def test_invalid_review_requests_do_not_partially_save(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        original = detail['detections']
        valid = {'op': 'update', 'detection_id': original[0]['detection_id'], 'class_id': 1}
        added = {'op': 'add', 'detection_id': str(uuid4()), 'class_id': 2, 'bbox_xyxy': [1, 2, 20, 30]}
        invalid = [
            {**added, 'op': 'replace'},
            {**added, 'detection_id': 'not-a-uuid'},
            {**added, 'detection_id': original[1]['detection_id']},
            {'op': 'delete', 'detection_id': 'DET-another-inspection'},
            {'op': 'update', 'detection_id': str(uuid4()), 'class_id': 2},
            {'op': 'delete', 'detection_id': original[0]['detection_id']},
            {k: v for k, v in added.items() if k != 'bbox_xyxy'},
            {k: v for k, v in added.items() if k != 'class_id'},
        ]
        invalid += [{**added, 'class_id': value} for value in (-1, 6, True, '2', 2.5)]
        invalid += [{**added, 'bbox_xyxy': value} for value in (
            [], [1, 2, 3], [-1, 2, 3, 4], [10, 2, 10, 4], [1, 10, 3, 4],
            [1, 2, 201, 4], [1, 2, 3, 201], [1, 2, float('nan'), 4],
            [1, 2, float('inf'), 4], [False, 2, 3, 4], ['1', 2, 3, 4],
        )]
        for correction in invalid:
            with self.subTest(correction=correction):
                payload = {'base_version': 0, 'review_status': 'corrected',
                           'corrections': [valid, correction]}
                response = self.client.post('/api/inspections/' + inspection_id + '/review',
                                            content=json.dumps(payload),
                                            headers={'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, 422, response.text)
                current = self.detail(inspection_id)
                self.assertEqual(current['review_version'], 0)
                self.assertEqual(current['detections'], original)
                self.assertIsNone(current['review'])
        for version in (None, -1, True, '0', 0.5):
            with self.subTest(base_version=version):
                payload = {'review_status': 'confirmed', 'corrections': []}
                if version is not None:
                    payload['base_version'] = version
                response = self.client.post('/api/inspections/' + inspection_id + '/review', json=payload)
                self.assertEqual(response.status_code, 422, response.text)

    def test_concurrent_reviews_accept_only_one_matching_version(self):
        inspection_id = self.upload()['inspection_id']
        barrier = threading.Barrier(2)

        def submit(index):
            with TestClient(app, raise_server_exceptions=False) as client:
                barrier.wait(timeout=5)
                return client.post('/api/inspections/' + inspection_id + '/review', json={
                    'review_status': 'confirmed', 'base_version': 0,
                    'notes': 'writer-%d' % index, 'corrections': [],
                }).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, (1, 2)))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.detail(inspection_id)['review_version'], 1)
        with storage.get_conn() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0], 1)

    def test_analysis_tracks_review_version_and_can_be_regenerated(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        url = '/api/inspections/' + inspection_id + '/analysis'
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.text)
        analysis = response.json()['analysis']
        self.assertEqual(analysis['source'], 'rule_fallback')
        self.assertEqual(analysis['review_version'], 0)
        self.assertFalse(analysis['stale'])
        self.assertTrue(analysis['created_at'])
        self.assertEqual(self.detail(inspection_id)['analysis'], analysis)
        response = self.review(inspection_id, 0, corrections=[
            {'op': 'add', 'detection_id': str(uuid4()), 'class_id': 5, 'bbox_xyxy': [0, 0, 20, 50]},
        ])
        self.assertEqual(response.status_code, 200, response.text)
        stale = self.detail(inspection_id)['analysis']
        self.assertEqual(stale['review_version'], 0)
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['facts'], analysis['facts'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.text)
        current = self.detail(inspection_id)['analysis']
        self.assertEqual(current['review_version'], 1)
        self.assertFalse(current['stale'])
        self.assertEqual(current['source'], 'rule_fallback')
        response = self.client.post('/api/chat/messages', json={
            'context_type': 'inspection', 'context_id': inspection_id, 'question': '有哪些缺陷？',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['source'], 'rule_fallback')
        self.assertTrue(response.json()['answer'])
        self.assertEqual(response.json()['review_version'], 1)
        self.assertFalse(response.json()['stale'])
        response = self.review(inspection_id, 1, corrections=[
            {'op': 'delete', 'detection_id': d['detection_id']} for d in detail['detections']
        ])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.detail(inspection_id)['reviewed_detections'], [])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.text)
        facts = ' '.join(response.json()['analysis']['facts'])
        self.assertIn('复核', facts)
        self.assertIn('原模型', facts)
        self.assertNotIn('本图未检出', facts)

    def test_chat_records_the_version_used_when_review_changes_during_answer(self):
        inspection_id = self.upload()['inspection_id']
        prompts = []

        def answer_after_review(system_prompt, user_prompt, **kwargs):
            prompts.append(user_prompt)
            storage.add_review(inspection_id, 'confirmed', 'other-operator',
                               {'corrections': [], 'notes': 'saved during chat'}, 0)
            return {'data': {'answer': 'Answer for the original review version', 'references': []}}

        with patch.object(llm, 'available', return_value=True), \
                patch.object(llm, 'source_name', return_value='deepseek'), \
                patch.object(llm, 'chat_json', side_effect=answer_after_review):
            response = self.client.post('/api/chat/messages', json={
                'context_type': 'inspection', 'context_id': inspection_id, 'question': '有哪些缺陷？',
            })
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['source'], 'deepseek')
        self.assertEqual(len(prompts), 1)
        self.assertIn('"review_version": 0', prompts[0])
        self.assertEqual(result['review_version'], 0)
        self.assertTrue(result['stale'])
        self.assertEqual(self.detail(inspection_id)['review_version'], 1)
        task = self.client.get('/api/tasks/' + result['task_id']).json()['result']
        self.assertEqual(task['review_version'], 0)
        self.assertTrue(task['stale'])
        response = self.client.post('/api/chat/messages', json={
            'context_type': 'batch', 'context_id': 'BATCH-A', 'question': '批次情况如何？',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['review_version'])
        self.assertFalse(response.json()['stale'])

    def test_report_id_keeps_its_saved_review_snapshot(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        response = self.client.post('/api/inspections/' + inspection_id + '/analysis')
        self.assertEqual(response.status_code, 200, response.text)
        response = self.review(inspection_id, 0, notes='manual-note-v1', corrections=[
            {'op': 'delete', 'detection_id': detail['detections'][0]['detection_id']},
        ])
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.get('/api/reports/' + inspection_id)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(saved['review_version'], 1)
        self.assertIn('manual-note-v1', saved['content_md'])
        self.assertIn('人工', saved['content_md'])
        self.assertIn('rule_fallback', saved['content_md'])
        self.assertIn('已过时', saved['content_md'])
        response = self.review(inspection_id, 1, notes='manual-note-v2', corrections=[])
        self.assertEqual(response.status_code, 200, response.text)
        frozen = self.client.get('/api/reports/' + saved['report_id']).json()
        self.assertEqual(frozen, saved)
        current = self.client.get('/api/reports/' + inspection_id).json()
        self.assertEqual(current['review_version'], 2)
        self.assertNotEqual(current['report_id'], saved['report_id'])
        self.assertIn('manual-note-v2', current['content_md'])

    def test_invalid_legacy_review_remains_readable_and_can_be_reset(self):
        detail = self.upload()
        inspection_id = detail['inspection_id']
        original = detail['detections']
        with storage.get_conn() as conn:
            conn.execute('INSERT INTO reviews (inspection_id,review_status,reviewer,payload_json,'
                         'base_version,created_at) VALUES (?,?,?,?,?,?)',
                         (inspection_id, 'corrected', 'legacy-client', json.dumps({
                             'corrections': [{'detection_id': original[0]['detection_id'], 'class_id': 99}],
                             'notes': 'legacy-invalid',
                         }), 0, storage.now()))
            conn.execute('UPDATE inspections SET review_status=?,review_version=1 WHERE inspection_id=?',
                         ('corrected', inspection_id))
        current = self.detail(inspection_id)
        self.assertTrue(current['review_invalid'])
        self.assertEqual(current['detections'], original)
        self.assertTrue(all(d['source'] == 'model' for d in current['reviewed_detections']))
        response = self.client.post('/api/inspections/' + inspection_id + '/analysis')
        self.assertEqual(response.status_code, 409, response.text)
        response = self.client.get('/api/reports/' + inspection_id)
        self.assertEqual(response.status_code, 409, response.text)
        response = self.review(inspection_id, 1, corrections=[])
        self.assertEqual(response.status_code, 200, response.text)
        current = self.detail(inspection_id)
        self.assertFalse(current.get('review_invalid', False))
        self.assertEqual(current['review_version'], 2)
        self.assertEqual(self.client.post('/api/inspections/' + inspection_id + '/analysis').status_code, 200)
        self.assertEqual(self.client.get('/api/reports/' + inspection_id).status_code, 200)

    def test_filtered_totals_and_batch_statistics_use_original_predictions(self):
        first = self.upload('BATCH-A')
        second = self.upload('BATCH-A')
        self.upload('BATCH-B')
        corrections = [
            {'op': 'update', 'detection_id': d['detection_id'], 'class_id': 5}
            for d in first['detections']
        ]
        response = self.review(first['inspection_id'], 0, corrections=corrections)
        self.assertEqual(response.status_code, 200, response.text)
        seen = set()
        for page in (1, 2):
            response = self.client.get('/api/inspections', params={
                'batch_no': 'BATCH-A', 'class_id': 2, 'page': page, 'page_size': 1,
            })
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['total'], 2)
            self.assertEqual(len(result['items']), 1)
            seen.add(result['items'][0]['inspection_id'])
        self.assertEqual(seen, {first['inspection_id'], second['inspection_id']})
        for params, total in (
            ({'batch_no': 'BATCH-B', 'class_id': 0}, 1),
            ({'review_status': 'corrected'}, 1),
            ({'batch_no': 'BATCH-A', 'review_status': 'pending'}, 1),
            ({'class_id': 5}, 0),
            ({'batch_no': 'missing'}, 0),
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get('/api/inspections', params=params).json()['total'], total)
        summary = self.client.get('/api/batches/BATCH-A/summary').json()
        self.assertEqual(summary['model_box_count'], 6)
        self.assertEqual(summary['per_class'], {'patches': 4, 'crazing': 2})
        self.assertEqual(summary['confirmed_count'], 1)

    def test_batch_summary_accepts_encoded_slashes_and_chinese(self):
        for batch in ('BATCH-A', 'B/1', '中文批次/一号'):
            with self.subTest(batch=batch):
                self.upload(batch)
                response = self.client.get('/api/batches/' + quote(batch, safe='') + '/summary')
                self.assertEqual(response.status_code, 200, response.text)
                summary = response.json()
                self.assertEqual(summary['batch_no'], batch)
                self.assertEqual(summary['image_count'], 1)
                self.assertEqual(summary['model_box_count'], 3)

    def test_failed_upload_rolls_back_all_records_and_removes_images(self):
        with storage.get_conn() as conn:
            conn.execute("CREATE TRIGGER fail_task BEFORE INSERT ON tasks "
                         "BEGIN SELECT RAISE(ABORT, 'injected test failure'); END")
        response = self.client.post('/api/inspections',
                                    files={'image': ('sample.png', self.image, 'image/png')},
                                    data={'batch_no': 'FAIL'})
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assert_empty_storage()
        with storage.get_conn() as conn:
            conn.execute('DROP TRIGGER fail_task')
        for filename, data in (('empty.png', b''), ('broken.png', b'not an image'),
                               ('wrong.gif', self.image)):
            with self.subTest(filename=filename):
                response = self.client.post('/api/inspections',
                                            files={'image': (filename, data, 'image/png')},
                                            data={'batch_no': 'INVALID'})
                self.assertEqual(response.status_code, 400, response.text)
                self.assert_empty_storage()


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        IMPORT_STORAGE.cleanup()
