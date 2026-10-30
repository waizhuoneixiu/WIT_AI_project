# -*- coding: utf-8 -*-
"""API Key 鉴权测试：设置 STEELSCAN_API_KEY 后验证 401/200 行为。

用法：python scripts/test_auth.py
"""
import os
import sys

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['STEELSCAN_API_KEY'] = 'test-key-123'
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
sys.path.insert(0, DEV)

from fastapi.testclient import TestClient  # noqa: E402

from server import app  # noqa: E402

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
        check(os.path.exists(info.get('weights', '')), '权重存在')

    test_dir = os.path.join(DEV, 'data', 'neu_det', 'images', 'test')
    sample = None
    if os.path.isdir(test_dir):
        names = sorted(os.listdir(test_dir))
        if names:
            sample = os.path.join(test_dir, names[0])

    if sample:
        print('\n== 无 Key POST /detect -> 401 ==')
        with open(sample, 'rb') as f:
            r = client.post('/detect', files={'image': (os.path.basename(sample), f, 'image/jpeg')})
        check(r.status_code == 401, 'HTTP 401（实际 %s）' % r.status_code)

        print('\n== 带 Key POST /detect -> 200 ==')
        with open(sample, 'rb') as f:
            r = client.post('/detect', files={'image': (os.path.basename(sample), f, 'image/jpeg')},
                            headers={'X-API-Key': TEST_KEY})
        check(r.status_code == 200, 'HTTP 200（实际 %s）' % r.status_code)
        if r.status_code == 200:
            res = r.json()
            check('defects' in res, '响应含 defects')
            print('  filename=%s defect_count=%s' % (res.get('filename'), res.get('defect_count')))

    print('\n== 错误 Key -> 401 ==')
    r = client.get('/model/info', headers={'X-API-Key': 'wrong-key'})
    check(r.status_code == 401, 'HTTP 401（实际 %s）' % r.status_code)

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
