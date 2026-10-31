# -*- coding: utf-8 -*-
"""API Key 鉴权测试：设置 STEELSCAN_API_KEY 后验证 401/200 行为。

用法：python scripts/test_auth.py
"""
import os
import sys
import tempfile
from unittest.mock import patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['STEELSCAN_API_KEY'] = 'test-key-123'
_storage = tempfile.TemporaryDirectory(prefix='steelscan_auth_')
os.environ['STEELSCAN_STORAGE_DIR'] = _storage.name
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
sys.path.insert(0, DEV)

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from server import app  # noqa: E402
import runtime  # noqa: E402
import storage  # noqa: E402

TEST_KEY = 'test-key-123'
failures = []


def check(cond, msg):
    print(('  [OK] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        failures.append(msg)


def main():
    client = TestClient(app)
    print('== /health（auth_required 应为 True） ==')
    h = client.get('/health').json()
    check(h.get('auth_required') is True, 'auth_required=True')
    print(h)

    print('\n== 无 Key 访问 /model/info -> 401 ==')
    r = client.get('/model/info')
    check(r.status_code == 401, 'HTTP 401（实际 %s）' % r.status_code)

    print('\n== 带 Key 访问 /model/info -> 200 ==')
    r = client.get('/model/info', headers={'X-API-Key': TEST_KEY})
    check(r.status_code == 200, 'HTTP 200（实际 %s）' % r.status_code)
    if r.status_code == 200:
        info = r.json()
        check(info.get('imgsz') == 640, 'imgsz=640')
        check(info.get('provider') == 'modelscope', '使用魔搭云模型，无需本地权重')

    import cv2
    import numpy as np
    _, sample = cv2.imencode('.png', np.zeros((20, 20, 3), np.uint8))
    with patch.object(runtime, 'get_detector') as detector:
        detector.return_value.detect.return_value = {'defects': [], 'defect_count': 0}
        print('\n== 无 Key POST /detect -> 401 ==')
        r = client.post('/detect', files={'image': ('test.png', sample.tobytes(), 'image/png')})
        check(r.status_code == 401, 'HTTP 401（实际 %s）' % r.status_code)

        print('\n== 带 Key POST /detect -> 200 ==')
        r = client.post('/detect', files={'image': ('test.png', sample.tobytes(), 'image/png')},
                        headers={'X-API-Key': TEST_KEY})
        check(r.status_code == 200, 'HTTP 200（实际 %s）' % r.status_code)
        if r.status_code == 200:
            res = r.json()
            check('defects' in res, '响应含 defects')
            print('  filename=%s defect_count=%s' % (res.get('filename'), res.get('defect_count')))

    with open(os.path.join(_storage.name, 'images', 'auth-test.png'), 'wb') as image:
        image.write(sample.tobytes())
    check(client.get('/files/auth-test.png').status_code == 401, '图片需要鉴权')
    check(client.get('/files/auth-test.png', headers={'X-API-Key': TEST_KEY}).status_code == 200,
          '正确 Key 可读图片')
    check(client.get('/files/..%5Csteelscan.db', headers={'X-API-Key': TEST_KEY}).status_code == 404,
          '拒绝图片路径穿越')

    print('\n== 错误 Key -> 401 ==')
    r = client.get('/model/info', headers={'X-API-Key': 'wrong-key'})
    check(r.status_code == 401, 'HTTP 401（实际 %s）' % r.status_code)

    print('\n== WebSocket 任务同样需要 Key ==')
    task_id = storage.new_id('TASK')
    storage.insert_task(task_id, 'detection', 'completed', result={'private_result': True})
    for headers, label in (({}, '缺少 Key'), ({'X-API-Key': 'wrong-key'}, '错误 Key')):
        try:
            with client.websocket_connect('/ws/tasks/' + task_id, headers=headers):
                check(False, label + ' 应在接受 WebSocket 前拒绝')
        except WebSocketDisconnect as exc:
            check(exc.code == 1008, label + ' WebSocket close 1008')
    with client.websocket_connect('/ws/tasks/' + task_id, headers={'X-API-Key': TEST_KEY}) as ws:
        check(ws.receive_json()['type'] == 'accepted', '正确 Key 收到 accepted')
        event = ws.receive_json()
        check(event['type'] == 'completed' and event['data']['result']['private_result'],
              '正确 Key 收到 completed 任务快照')

    print('\n== 结论 ==')
    if failures:
        print('FAILED: %d' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('全部通过 ✔')
    return 0


if __name__ == '__main__':
    sys.exit(main())
