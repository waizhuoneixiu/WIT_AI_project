# -*- coding: utf-8 -*-
"""团队共同接口（/api）端到端自检：检测→任务→详情→分析→问答→复核→统计→报告→WS。

用法：python scripts/test_api_contract.py
使用临时 SQLite 存储，不污染正式数据；返回码 0 表示全部通过。
"""
import json
import os
import shutil
import sys
import tempfile

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
os.environ.setdefault('MPLCONFIGDIR', os.path.join(DEV, '.mpl'))
TMP_DIR = tempfile.mkdtemp(prefix='steelscan_test_')
os.environ['STEELSCAN_STORAGE_DIR'] = TMP_DIR

sys.path.insert(0, DEV)

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from server import app  # noqa: E402

failures = []


def check(cond, msg):
    print(('  [OK] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        failures.append(msg)


def sample_image():
    test_dir = os.path.join(config.DATA_DIR, 'images', 'test')
    if not os.path.isdir(test_dir):
        return None
    names = sorted(os.listdir(test_dir))
    for n in names:
        if n.startswith('patches'):
            return os.path.join(test_dir, n)
    return os.path.join(test_dir, names[0]) if names else None


def main():
    client = TestClient(app)
    img = sample_image()
    if not img:
        print('找不到测试图片，跳过')
        return 1
    batch = 'TEST-BATCH-001'

    print('== GET /api/class-map（契约类别映射） ==')
    r = client.get('/api/class-map')
    check(r.status_code == 200, 'HTTP 200')
    cmap = r.json()
    check(len(cmap.get('contract_classes', [])) == 6, '契约类别 6 个')
    check([c['class_id'] for c in cmap['contract_classes']] == [0, 1, 2, 3, 4, 5], 'class_id 0~5 连续')

    print('\n== POST /api/inspections（上传+检测+落库） ==')
    with open(img, 'rb') as f:
        r = client.post('/api/inspections', files={'image': (os.path.basename(img), f, 'image/jpeg')},
                        data={'batch_no': batch, 'workpiece_no': 'W-0001'})
    check(r.status_code == 201, 'HTTP 201（实际 %s）' % r.status_code)
    created = r.json()
    inspection_id = created.get('inspection_id')
    task_id = created.get('task_id')
    check(bool(inspection_id), '返回 inspection_id')
    check(bool(task_id), '返回 task_id')
    print(json.dumps(created, ensure_ascii=False))

    print('\n== GET /api/tasks/{task_id} ==')
    r = client.get('/api/tasks/%s' % task_id)
    check(r.status_code == 200, 'HTTP 200')
    task = r.json()
    check(task.get('status') == 'completed', '检测任务 completed')
    check('result' in task, '任务包含 result')

    print('\n== GET /api/inspections/{id} ==')
    r = client.get('/api/inspections/%s' % inspection_id)
    check(r.status_code == 200, 'HTTP 200')
    detail = r.json()
    check(detail.get('image_width') == 200 and detail.get('image_height') == 200, '原图尺寸 200x200')
    check(len(detail.get('detections', [])) >= 1, '至少 1 个检测框')
    d0 = detail['detections'][0]
    check(set(('detection_id', 'class_id', 'class_name', 'score', 'bbox_xyxy')).issubset(d0.keys()),
          '框字段符合契约')
    check(isinstance(d0['bbox_xyxy'], list) and len(d0['bbox_xyxy']) == 4, 'bbox_xyxy 4 个值')
    check(detail.get('review_status') == 'pending', '初始复核状态 pending')

    print('\n== GET /api/inspections（列表查询） ==')
    r = client.get('/api/inspections', params={'batch_no': batch, 'page': 1, 'page_size': 10})
    check(r.status_code == 200, 'HTTP 200')
    listed = r.json()
    check(listed.get('total', 0) >= 1, 'total >= 1')
    check(listed['items'][0]['inspection_id'] == inspection_id, '列表含刚创建记录')

    print('\n== POST /api/inspections/{id}/analysis ==')
    r = client.post('/api/inspections/%s/analysis' % inspection_id)
    check(r.status_code == 200, 'HTTP 200')
    analysis = r.json()
    keys = ('facts', 'references', 'hypotheses', 'recheck_steps', 'missing_information')
    check(all(k in analysis.get('analysis', {}) for k in keys), '分析含事实/引用/原因/复检/待补信息')

    print('\n== POST /api/chat/messages ==')
    r = client.post('/api/chat/messages', json={'context_type': 'inspection',
                                                'context_id': inspection_id,
                                                'question': '这张图有什么缺陷？给出复检建议'})
    check(r.status_code == 200, 'HTTP 200')
    chat = r.json()
    check(bool(chat.get('answer')), '返回回答')
    check(chat.get('status') == 'completed', '问答任务 completed')

    print('\n== POST /api/inspections/{id}/review（版本校验） ==')
    r = client.post('/api/inspections/%s/review' % inspection_id,
                    json={'review_status': 'confirmed', 'reviewer': 'operator-1',
                          'notes': '复判通过', 'base_version': 0})
    check(r.status_code == 200, '首次复核 HTTP 200')
    check(r.json().get('review_version') == 1, 'review_version=1')
    r2 = client.post('/api/inspections/%s/review' % inspection_id,
                     json={'review_status': 'corrected', 'reviewer': 'operator-1', 'base_version': 0})
    check(r2.status_code == 409, '旧版本提交被拒绝（409）')
    r3 = client.post('/api/inspections/%s/review' % inspection_id,
                     json={'review_status': 'corrected', 'reviewer': 'operator-1',
                           'corrections': [{'detection_id': d0['detection_id'], 'class_id': 2}],
                           'base_version': 1})
    check(r3.status_code == 200, '新版本复核 HTTP 200')

    print('\n== GET /api/batches/{batch_no}/summary ==')
    r = client.get('/api/batches/%s/summary' % batch)
    check(r.status_code == 200, 'HTTP 200')
    summary = r.json()
    check(summary.get('image_count') == 1, '图片数=1')
    check(summary.get('model_box_count', 0) >= 1, '模型框数 >= 1')
    check('per_class' in summary, '含分类统计')

    print('\n== GET /api/reports/{id} ==')
    r = client.get('/api/reports/%s' % inspection_id)
    check(r.status_code == 200, 'HTTP 200')
    report = r.json()
    check('质检报告' in report.get('content_md', ''), '报告含标题')

    print('\n== WS /ws/tasks/{task_id} ==')
    try:
        with client.websocket_connect('/ws/tasks/%s' % task_id) as ws:
            ev1 = ws.receive_json()
            check(ev1.get('type') == 'accepted', '收到 accepted 事件')
            ev2 = ws.receive_json()
            check(ev2.get('type') == 'completed', '收到 completed 事件')
    except Exception as e:  # noqa: BLE001
        check(False, 'WebSocket 失败: %r' % e)

    print('\n== 404 行为 ==')
    check(client.get('/api/inspections/INSP-NOT-EXIST').status_code == 404, '不存在记录返回 404')
    check(client.get('/api/tasks/TASK-NOT-EXIST').status_code == 404, '不存在任务返回 404')

    print('\n== 结论 ==')
    if failures:
        print('FAILED: %d' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('全部通过 ✔')
    return 0


if __name__ == '__main__':
    try:
        code = main()
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    sys.exit(code)
