"""Cloud protocol and startup checks; no network, credentials or model packages needed."""
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import requests
from urllib3.exceptions import ReadTimeoutError

import config
import runtime
from cloud_detector import DetectionError, ModelScopeDetector, validate_result


def cloud_result():
    return {'width': 80, 'height': 60, 'imgsz': 640, 'defect_count': 1,
            'inference_ms': 20, 'defects': [{'class_id': 2, 'class_name': 'patches',
            'confidence': .8, 'bbox_xyxy': [1, 2, 30, 40]}]}


class Response:
    def __init__(self, data=None, lines=None, status=200):
        self.status_code = status
        self.data = data
        self.lines = lines or []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def iter_content(self, **kwargs):
        raw = ('\n'.join(self.lines) + '\n').encode() if self.lines else json.dumps(self.data).encode()
        size = kwargs.get('chunk_size', 4096)
        for start in range(0, len(raw), size):
            yield raw[start:start+size]

class CloudAdapterTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.multiple(config, MODELSCOPE_API_TOKEN='secret-test-token',
                                          MODELSCOPE_TIMEOUT=60.0,
                                          DETECTOR_PROVIDER='modelscope')
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.detector = ModelScopeDetector()
        self.image = np.zeros((60, 80, 3), dtype=np.uint8)

    def responses(self, result=None):
        result = cloud_result() if result is None else result
        return [Response(['/tmp/gradio/image.png']), Response({'event_id': 'event-123'}),
                Response(lines=['event: heartbeat', 'data: null', '', 'event: complete',
                                'data: ' + json.dumps([None, json.dumps(result), [], 'summary']), ''])]

    def detect(self, responses):
        with patch('cloud_detector.requests.Session') as session_factory:
            session = session_factory.return_value.__enter__.return_value
            session.request.side_effect = responses
            result = self.detector.detect(self.image)
            return result, session

    def test_upload_call_sse_preserves_contract(self):
        responses = self.responses()
        result, session = self.detect(responses)
        self.assertEqual(result['model'], 'yolo26n-640-onnx')
        self.assertEqual(result['defects'][0]['class_id'], 2)
        self.assertEqual(result['defects'][0]['class_cn'], '斑块')
        self.assertEqual(session.request.call_count, 3)
        upload = session.request.call_args_list[0]
        self.assertEqual(upload.kwargs['files']['files'][2], 'image/png')
        self.assertTrue(upload.kwargs['files']['files'][1].startswith(b'\x89PNG'))
        self.assertFalse(upload.kwargs['allow_redirects'])
        self.assertEqual(session.request.call_args_list[1].kwargs['json']['data'][1], .25)
        self.assertTrue(all(response.closed for response in responses))

    def test_explicit_empty_result_is_valid(self):
        result = cloud_result()
        result.update(defect_count=0, defects=[])
        actual, _ = self.detect(self.responses(result))
        self.assertEqual(actual['defects'], [])

    def test_malformed_results_never_become_empty_success(self):
        mutations = [lambda r: r.pop('defects'), lambda r: r.update(width=81),
                     lambda r: r.update(defect_count=0), lambda r: r.update(inference_ms=-1),
                     lambda r: r['defects'][0].update(class_id=1),
                     lambda r: r['defects'][0].update(confidence=float('nan')),
                     lambda r: r['defects'][0].update(class_id=True),
                     lambda r: r['defects'][0].update(bbox_xyxy=[0, 0, 81, 60]),
                     lambda r: r['defects'][0].update(bbox_xyxy=[20, 2, 1, 40])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                result = copy.deepcopy(cloud_result())
                mutate(result)
                with self.assertRaises(DetectionError) as error:
                    validate_result(result, 80, 60)
                self.assertEqual(error.exception.status_code, 502)

    def test_cloud_errors_are_safe(self):
        cases = [([Response(status=401)], 503), ([Response(status=302)], 502),
                 ([requests.Timeout('secret-test-token')], 504),
                 ([requests.ConnectionError(ReadTimeoutError(None, None, 'secret-test-token'))], 504),
                 ([requests.ConnectionError('secret-test-token')], 502),
                 ([Response({})], 502),
                 ([Response(['/tmp/x']), Response({'event_id': '../evil'})], 502),
                 ([Response(['/tmp/x']), Response({'event_id': 'ok'}),
                   Response(lines=['event: error', 'data: "secret-test-token"', ''])], 502)]
        for responses, status in cases:
            with self.subTest(status=status, responses=responses):
                with self.assertRaises(DetectionError) as error:
                    self.detect(responses)
                self.assertEqual(error.exception.status_code, status)
                self.assertNotIn('secret-test-token', str(error.exception))

    def test_missing_completion_is_error(self):
        with self.assertRaises(DetectionError):
            self.detect([Response(['/tmp/x']), Response({'event_id': 'ok'}),
                         Response(lines=['event: heartbeat', 'data: null', ''])])

    def test_configuration_and_parameters_fail_before_network(self):
        for url in ['http://example.com', 'https://evil.com',
                    'https://good.api-inference.modelscope.net.evil.com',
                    'https://good.api-inference.modelscope.net:bad', 'https://[bad']:
            self.detector.base_url = url
            with self.assertRaises(DetectionError) as error:
                self.detector.detect(self.image)
            self.assertEqual(error.exception.status_code, 503)
        self.detector = ModelScopeDetector()
        with self.assertRaises(DetectionError) as error:
            self.detector.detect(self.image, imgsz=320)
        self.assertEqual(error.exception.status_code, 422)
        self.detector.token = ''
        with self.assertRaises(DetectionError) as error:
            self.detector.detect(self.image)
        self.assertEqual(error.exception.status_code, 503)

    def test_deadline_and_response_limit(self):
        with self.assertRaises(DetectionError) as error:
            self.detector._remaining(time.monotonic() - 1)
        self.assertEqual(error.exception.status_code, 504)
        with patch('cloud_detector.MAX_RESPONSE_BYTES', 64):
            with self.assertRaises(DetectionError) as error:
                self.detector._completion(Response(lines=['data: ' + 'x' * 100]),
                                          time.monotonic() + 60)
        self.assertEqual(error.exception.status_code, 502)

    def test_long_sse_line_is_bounded_and_linear(self):
        payload = [None, json.dumps(cloud_result()), [], 'x' * 500_000]
        response = Response(lines=['event: complete', 'data: ' + json.dumps(payload), ''])
        start = time.monotonic()
        result = self.detector._completion(response, start + 5)
        self.assertEqual(result['defect_count'], 1)
        self.assertLess(time.monotonic() - start, 3)

    def test_small_sse_heartbeats_do_not_hide_deadline(self):
        class Heartbeats(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(15):
                        self.wfile.write(b'event: heartbeat\ndata: null\n\n')
                        self.wfile.flush()
                        time.sleep(.1)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Heartbeats)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            response = requests.get('http://127.0.0.1:%d' % server.server_port, stream=True, timeout=2)
            start = time.monotonic()
            with self.assertRaises(DetectionError) as error:
                self.detector._completion(response, start + .2)
            self.assertEqual(error.exception.status_code, 504)
            self.assertLess(time.monotonic() - start, .8)
        finally:
            thread.join(timeout=3)
            server.server_close()

    def test_cloud_runtime_does_not_select_weights(self):
        with patch.object(runtime, '_detector', None), patch.object(runtime, 'pick_weights') as weights:
            self.assertIsInstance(runtime.get_detector(), ModelScopeDetector)
            self.assertEqual(runtime.model_info()['model_version'], 'yolo26n-640-onnx')
            weights.assert_not_called()

    def test_dotenv_is_loaded_before_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(config.__file__).read_text(encoding='utf-8')
            (Path(directory) / 'config.py').write_text(source, encoding='utf-8')
            (Path(directory) / '.env').write_text('STEELSCAN_API_KEY=dotenv-test\n', encoding='utf-8')
            env = {key: value for key, value in os.environ.items() if key != 'STEELSCAN_API_KEY'}
            process = subprocess.run([sys.executable, '-c',
                                      "import config; assert config.API_KEY == 'dotenv-test'"],
                                     cwd=directory, env=env, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == '__main__':
    unittest.main()
