# -*- coding: utf-8 -*-
"""Export actual API responses using temporary storage and disabled cloud LLM calls.

python scripts/export_api_samples.py --fixture   # synthetic, no network/model libraries
python scripts/export_api_samples.py             # real ModelScope inference on a bundled sample
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'api_samples'


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def export(client, image_name, image_data, fixture):
    def request(name, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        result = response.json()
        save(name, result)
        return result

    batch = 'FIXTURE-BATCH-001' if fixture else 'SAMPLE-BATCH-001'
    for name, path in [('health', '/health'), ('classes', '/classes'),
                       ('class_map', '/api/class-map'), ('llm_info', '/api/llm/info')]:
        request(name + '.json', 'GET', path)
    created = request('inspection_created.json', 'POST', '/api/inspections',
                      files={'image': (image_name, image_data, 'image/png' if fixture else 'image/jpeg')},
                      data={'batch_no': batch, 'workpiece_no': 'SAMPLE-W1'})
    inspection_path = '/api/inspections/' + created['inspection_id']
    initial = request('inspection_detail.json', 'GET', inspection_path)
    assert initial['review_version'] == 0 and initial['analysis'] is None
    assert initial['detections'], 'Choose an image with at least one model detection.'
    if fixture:
        assert initial['model_version'] == 'fixture-not-yolo'
    request('task.json', 'GET', '/api/tasks/' + created['task_id'])
    request('inspection_list.json', 'GET', '/api/inspections', params={'batch_no': batch})
    analysis = request('analysis.json', 'POST', inspection_path + '/analysis')
    assert analysis['analysis']['source'] == 'rule_fallback'
    assert analysis['analysis']['review_version'] == 0 and not analysis['analysis']['stale']

    original_id = initial['detections'][0]['detection_id']
    width, height = initial['image_width'], initial['image_height']
    added = {'op': 'add', 'detection_id': 'e41c00b2-0ac6-4fd3-9932-6931b4d978ab',
             'class_id': 5, 'bbox_xyxy': [width * .75, height * .1, width * .9, height * .8]}
    corrections = [
        {'op': 'update', 'detection_id': original_id, 'class_id': 1,
         'bbox_xyxy': [width * .15, height * .2, width * .65, height * .7]},
        added,
    ]
    review_body = {'review_status': 'corrected', 'reviewer': 'sample-operator',
                   'notes': '示例：调整原框并补充人工框', 'base_version': 0, 'corrections': corrections}
    save('review_request.json', review_body)
    review = request('review.json', 'POST', inspection_path + '/review', json=review_body)
    assert review['review_version'] == 1
    reviewed = request('inspection_reviewed.json', 'GET', inspection_path)
    assert reviewed['detections'] == initial['detections']
    assert reviewed['analysis']['stale'] and reviewed['analysis']['review_version'] == 0
    edited_ids = {original_id, added['detection_id']}
    edited = [d for d in reviewed['reviewed_detections'] if d['detection_id'] in edited_ids]
    assert len(edited) == 2 and all(d['source'] == 'manual' and d['score'] is None for d in edited)
    analysis = request('analysis_after_review.json', 'POST', inspection_path + '/analysis')
    assert analysis['analysis']['review_version'] == 1 and not analysis['analysis']['stale']
    old_report = request('report_before_delete.json', 'GET', '/api/reports/' + created['inspection_id'])
    assert old_report['review_version'] == 1

    # The complete second snapshot retains the added box while deleting the original.
    delete_body = dict(review_body, base_version=1, notes='示例：删除原框，保留上次人工新增框',
                       corrections=[{'op': 'delete', 'detection_id': original_id}, added])
    save('review_delete_request.json', delete_body)
    review = request('review_delete.json', 'POST', inspection_path + '/review', json=delete_body)
    assert review['review_version'] == 2
    deleted = request('inspection_after_delete.json', 'GET', inspection_path)
    assert deleted['detections'] == initial['detections']
    assert deleted['analysis']['stale'] and deleted['analysis']['review_version'] == 1
    assert original_id not in {d['detection_id'] for d in deleted['reviewed_detections']}
    assert added['detection_id'] in {d['detection_id'] for d in deleted['reviewed_detections']}
    analysis = request('analysis_after_delete.json', 'POST', inspection_path + '/analysis')
    assert analysis['analysis']['review_version'] == 2 and not analysis['analysis']['stale']
    final = request('inspection_final.json', 'GET', inspection_path)
    assert final['review_version'] == 2 and not final['analysis']['stale']
    chat = request('chat.json', 'POST', '/api/chat/messages', json={
        'context_type': 'inspection', 'context_id': created['inspection_id'],
        'question': '当前人工复核结果应如何复检？'})
    assert chat['source'] == 'rule_fallback'
    assert chat['review_version'] == 2 and chat['stale'] is False
    chat_task = request('chat_task.json', 'GET', '/api/tasks/' + chat['task_id'])
    assert chat_task['result']['review_version'] == 2 and chat_task['result']['stale'] is False
    batch_chat = request('chat_batch.json', 'POST', '/api/chat/messages', json={
        'context_type': 'batch', 'context_id': batch, 'question': '这个批次的原模型检测统计是什么？'})
    assert batch_chat['review_version'] is None and batch_chat['stale'] is False
    summary = request('batch_summary.json', 'GET', '/api/batches/' + batch + '/summary')
    assert summary['model_box_count'] == len(initial['detections'])
    assert summary['confirmed_count'] == 1
    report = request('report.json', 'GET', '/api/reports/' + created['inspection_id'])
    assert report['format'] == 'md' and report['review_version'] == 2
    assert '## 辅助分析' in report['content_md'] and 'rule_fallback' in report['content_md']
    historical = request('report_historical.json', 'GET', '/api/reports/' + old_report['report_id'])
    assert historical == old_report
    assert client.get(final['original_url']).status_code == 200
    if fixture:
        assert summary['per_class'] == {'patches': 1}
        assert len(final['reviewed_detections']) == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', action='store_true', help='use explicit synthetic detection; never call the cloud')
    parser.add_argument('--image', type=Path, default=ROOT / 'deploy' / 'modelscope_package' / 'samples' / 'patches_110.jpg',
                        help='real-mode image; defaults to the bundled public deployment sample')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix='steelscan-api-samples-') as directory, ExitStack() as stack:
        environment = {
            'STEELSCAN_STORAGE_DIR': directory, 'STEELSCAN_DB': str(Path(directory) / 'samples.db'),
            'STEELSCAN_API_KEY': '', 'DETECTOR_PROVIDER': 'modelscope',
            'LLM_PROVIDER': 'deepseek', 'DEEPSEEK_API_KEY': '', 'OPENAI_API_KEY': '',
            'DEEPSEEK_MODEL': 'deepseek-chat', 'DEEPSEEK_BASE_URL': 'https://api.deepseek.com',
            'LOCAL_LLM_MODEL': 'models/not-installed',
        }
        if args.fixture:
            environment['MODELSCOPE_API_TOKEN'] = ''
        stack.enter_context(patch.dict(os.environ, environment))
        from fastapi.testclient import TestClient
        import llm
        import runtime
        from server import app
        assert not llm.available(), 'Sample export must not call a cloud or local LLM.'
        if args.fixture:
            import cv2
            import numpy as np
            sys.path.insert(0, str(ROOT / 'tests'))
            from fixture_server import FixtureDetector
            stack.enter_context(patch.object(runtime, 'get_detector', return_value=FixtureDetector()))
            stack.enter_context(patch.object(runtime, 'model_info', return_value={
                'provider': 'test-fixture', 'configured': True, 'model_version': 'fixture-not-yolo'}))
            stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('Fixture export forbids network calls.')))
            encoded, image = cv2.imencode('.png', np.full((200, 200, 3), 210, dtype=np.uint8))
            assert encoded
            image_name, image_data = 'fixture-synthetic.png', image.tobytes()
        else:
            image_name, image_data = args.image.name, args.image.read_bytes()
        with TestClient(app) as client:
            export(client, image_name, image_data, args.fixture)
        mode = '合成夹具（fixture-not-yolo）；没有调用魔搭、DeepSeek或本地模型' if args.fixture else '真实魔搭检测；分析与问答强制使用规则模板'
        (OUT / 'README.md').write_text(
            '# API 响应样例\n\n'
            f'本次导出模式：**{mode}**。所有响应JSON由当前业务API的TestClient实际返回，'
            '不是手写响应；`*_request.json`是对应复核请求。记录仅存在于临时SQLite，导出结束后删除。\n\n'
            '运行：`python scripts/export_api_samples.py --fixture`。去掉`--fixture`会调用真实魔搭，'
            '默认图片为部署包公开样例；两种模式均禁用大模型调用。\n\n'
            '流程：初始检测/详情/分析（v0）→ update+add复核（v1）→ 旧分析stale与新分析/报告 '
            '→ delete原框并保留add（v2）→ 旧分析stale、新分析、最终详情/报告与旧报告回读。'
            '`batch_summary`仍统计原模型框。`chat`及`chat_task`包含实际上下文review_version/stale，'
            '`chat_batch`的review_version为null。脚本对版本、不可变原预测、人工框分数、stale和报告历史作断言。\n\n'
            '图片URL和记录编号仅是本次临时样例，不对应可访问的持久服务。合成结果不能用于模型精度、'
            '云连通性或Android设备验收；source=rule_fallback不能称为真实大模型生成。\n', encoding='utf-8')
    print('Exported API samples to', OUT, '(fixture)' if args.fixture else '(real cloud detection)')


if __name__ == '__main__':
    main()
