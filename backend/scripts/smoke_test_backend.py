# -*- coding: utf-8 -*-
"""后端自检脚本（无需启动端口，直接 TestClient 验证 API + 真实推理）。

用法：
    python scripts/smoke_test_backend.py
返回码 0 表示全部通过。
"""
import json
import os
import sys

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
os.environ.setdefault('MPLCONFIGDIR', os.path.join(DEV, '.mpl'))
if DEV not in sys.path:
    sys.path.insert(0, DEV)

from fastapi.testclient import TestClient  # noqa: E402

from server import app  # noqa: E402

failures = []


def check(cond, msg):
    print(('  [OK] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        failures.append(msg)


def main():
    client = TestClient(app)
    print('== /health ==')
    r = client.get('/health')
    check(r.status_code == 200, 'HTTP 200')
    h = r.json()
    check(h.get('status') == 'ok', 'status=ok')
    print(json.dumps(h, ensure_ascii=False))

    print('\n== /classes ==')
    r = client.get('/classes')
    check(r.status_code == 200, 'HTTP 200')
    classes = r.json().get('classes', [])
    check(len(classes) == 6, '6 个类别')
    check([c['name'] for c in classes] == ['crazing', 'inclusion', 'patches',
                                           'pitted_surface', 'rolled-in_scale', 'scratches'],
          '类别顺序按团队契约（04-shared-contract）')

    print('\n== /model/info ==')
    r = client.get('/model/info')
    check(r.status_code == 200, 'HTTP 200')
    info = r.json()
    check(os.path.exists(info.get('weights', '')), '权重文件存在: %s' % os.path.basename(info.get('weights', '')))
    check(info.get('imgsz') == 640, '输入尺寸=640')
    check(info.get('weights_file') == 'best.pt', '使用 best.pt')
    print(json.dumps(info, ensure_ascii=False))

    print('\n== POST /detect（真实推理） ==')
    test_dir = os.path.join(DEV, 'data', 'neu_det', 'images', 'test')
    sample = None
    if os.path.isdir(test_dir):
        for name in sorted(os.listdir(test_dir)):
            if name.startswith('patches'):
                sample = os.path.join(test_dir, name)
                break
        if sample is None:
            sample = os.path.join(test_dir, sorted(os.listdir(test_dir))[0])
    check(sample is not None, '找到测试图片')
    if sample:
        with open(sample, 'rb') as f:
            r = client.post('/detect', files={'image': (os.path.basename(sample), f, 'image/jpeg')})
        check(r.status_code == 200, 'HTTP 200')
        res = r.json()
        check('defects' in res and isinstance(res['defects'], list), '响应包含 defects 列表')
        check(res.get('model') == 'best.pt', 'model=best.pt')
        print(json.dumps({'filename': res.get('filename'), 'defect_count': res.get('defect_count'),
                          'defects': [{k: d[k] for k in ('class_name', 'class_cn', 'confidence')} for d in res.get('defects', [])],
                          'inference_ms': res.get('inference_ms')}, ensure_ascii=False, indent=2))

    print('\n== POST /detect/base64（conf 覆盖） ==')
    if sample:
        import base64
        with open(sample, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        r = client.post('/detect/base64', json={'image_base64': b64, 'filename': os.path.basename(sample), 'conf': 0.10})
        check(r.status_code == 200, 'HTTP 200')
        res = r.json()
        check(res.get('defect_count', 0) >= 1, 'conf=0.10 时至少检出 1 个缺陷')
        print(json.dumps({'defect_count': res.get('defect_count'), 'inference_ms': res.get('inference_ms')}, ensure_ascii=False))

    print('\n== 接口文档 ==')
    doc = os.path.join(DEV, 'docs', 'API接口文档.md')
    spec = os.path.join(DEV, 'docs', 'openapi.json')
    check(os.path.exists(doc), 'docs/API接口文档.md 存在')
    check(os.path.exists(spec), 'docs/openapi.json 存在')
    if os.path.exists(spec):
        with open(spec, encoding='utf-8') as f:
            s = json.load(f)
        paths = s.get('paths', {})
        check(len(paths) >= 15, 'OpenAPI 包含 >=15 个路径（实际 %d 个）' % len(paths))
        check(all(p in paths for p in ('/api/inspections', '/detect', '/health')),
              'OpenAPI 含核心接口（/api/inspections、/detect、/health）')

    print('\n== 结论 ==')
    if failures:
        print('FAILED: %d 项' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('全部通过 ✔')
    return 0


if __name__ == '__main__':
    sys.exit(main())
