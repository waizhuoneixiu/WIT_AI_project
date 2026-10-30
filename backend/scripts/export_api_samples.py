# -*- coding: utf-8 -*-
"""导出真实接口响应样例（给 App 开发 mock / 材料截图用）。

运行：python scripts/export_api_samples.py
输出：docs/api_samples/*.json
"""
import json
import os
import shutil
import sys
import tempfile

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
os.environ.setdefault('MPLCONFIGDIR', os.path.join(DEV, '.mpl'))
TMP = tempfile.mkdtemp(prefix='steelscan_samples_')
os.environ['STEELSCAN_STORAGE_DIR'] = TMP
os.environ['STEELSCAN_DB'] = os.path.join(TMP, 'samples.db')
sys.path.insert(0, DEV)

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from server import app  # noqa: E402

OUT = os.path.join(DEV, 'docs', 'api_samples')


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print('  saved', name)


def main():
    client = TestClient(app)
    test_dir = os.path.join(config.DATA_DIR, 'images', 'test')
    names = sorted(n for n in os.listdir(test_dir) if n.lower().endswith('.jpg'))
    sample = next((n for n in names if n.startswith('patches')), names[0])
    sample_path = os.path.join(test_dir, sample)
    batch = 'SAMPLE-BATCH-001'

    save('health.json', client.get('/health').json())
    save('classes.json', client.get('/classes').json())
    save('class_map.json', client.get('/api/class-map').json())
    save('llm_info.json', client.get('/api/llm/info').json())

    with open(sample_path, 'rb') as f:
        created = client.post('/api/inspections',
                              files={'image': (sample, f, 'image/jpeg')},
                              data={'batch_no': batch, 'workpiece_no': 'SAMPLE-W1'}).json()
    save('inspection_created.json', created)
    insp = created['inspection_id']
    task = created['task_id']

    save('inspection_detail.json', client.get('/api/inspections/%s' % insp).json())
    save('task.json', client.get('/api/tasks/%s' % task).json())
    save('inspection_list.json', client.get('/api/inspections', params={'batch_no': batch}).json())
    save('analysis.json', client.post('/api/inspections/%s/analysis' % insp).json())
    save('chat.json', client.post('/api/chat/messages', json={
        'context_type': 'inspection', 'context_id': insp,
        'question': '这张图有什么缺陷？可能原因和复检建议是什么？'}).json())
    save('review.json', client.post('/api/inspections/%s/review' % insp, json={
        'review_status': 'confirmed', 'reviewer': 'demo-operator',
        'notes': '示例复核', 'base_version': 0}).json())
    save('batch_summary.json', client.get('/api/batches/%s/summary' % batch).json())
    save('report.json', client.get('/api/reports/%s' % insp).json())
    print('\n样例已导出到:', OUT)


if __name__ == '__main__':
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
