# -*- coding: utf-8 -*-
"""DeepSeek 大模型集成自检（无需真实 Key；如配置了 Key 会额外做一次真实调用）。

覆盖：
1) LLM 成功路径 -> analysis/chat 返回 source=deepseek
2) LLM 异常 -> 自动降级规则模板 source=rule_fallback
3) 未配置 Key -> 降级规则模板
4) /api/llm/info 状态字段
用法：python scripts/test_llm.py
"""
import os
import sys
import tempfile

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
os.environ.setdefault('MPLCONFIGDIR', os.path.join(DEV, '.mpl'))
TMP = tempfile.mkdtemp(prefix='steelscan_llm_test_')
os.environ['STEELSCAN_STORAGE_DIR'] = TMP
sys.path.insert(0, DEV)

import api_v1  # noqa: E402
import llm  # noqa: E402
import storage  # noqa: E402

storage.init_db()

failures = []


def check(cond, msg):
    print(('  [OK] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        failures.append(msg)


DET = [{'class_id': 2, 'class_name': 'patches', 'class_cn': '斑块',
        'confidence': 0.88, 'bbox_xyxy': [62.2, 68.4, 136.2, 160.8]}]

FAKE_OK = {
    'data': {
        'facts': ['检出斑块 1 处'],
        'references': ['斑块知识条目'],
        'hypotheses': ['可能为局部氧化/酸洗不均，建议核实'],
        'recheck_steps': ['复核图像与同批次记录'],
        'missing_information': ['工艺参数'],
    },
    'model': 'deepseek-chat',
    'latency_ms': 12.3,
    'tokens': {'total_tokens': 100},
}


def main():
    orig_available = llm.available
    orig_chat = llm.chat_json
    orig_source = llm.source_name

    print('== 1) 未配置 Key -> 规则降级 ==')
    api_v1.llm.available = lambda: False
    out = api_v1._analysis_for(DET, 'INSP-TEST', 'pending')
    check(out.get('source') == 'rule_fallback', 'analysis source=rule_fallback')
    check(all(k in out for k in ('facts', 'references', 'hypotheses', 'recheck_steps', 'missing_information')),
          '降级结果字段完整')

    print('\n== 2) 大模型成功 -> source=deepseek ==')
    api_v1.llm.available = lambda: True
    api_v1.llm.source_name = lambda: 'deepseek'
    api_v1.llm.chat_json = lambda *a, **k: dict(FAKE_OK)
    out = api_v1._analysis_for(DET, 'INSP-TEST', 'pending')
    check(out.get('source') == 'deepseek', 'analysis source=deepseek')
    check(out.get('model') == 'deepseek-chat', '记录模型名')
    check(out['facts'] == ['检出斑块 1 处'], '使用大模型 facts')

    # chat 走 batch 上下文（mock storage.batch_summary）
    orig_summary = api_v1.storage.batch_summary
    api_v1.storage.batch_summary = lambda b: {'batch_no': b, 'image_count': 3, 'model_box_count': 5,
                                              'per_class': {'patches': 5}, 'review_stats': {},
                                              'confirmed_count': 0, 'unresolved_count': 0}
    api_v1.llm.chat_json = lambda *a, **k: {'data': {'answer': '这是大模型回答', 'references': ['数据依据']},
                                            'model': 'deepseek-chat', 'latency_ms': 8.0, 'tokens': {}}
    answer, refs, source = api_v1._answer_question('batch', 'B-1', '有什么缺陷？')
    check(source == 'deepseek', 'chat source=deepseek')
    check(answer == '这是大模型回答', '使用大模型回答')
    check(refs == ['数据依据'], '使用大模型引用')
    api_v1.storage.batch_summary = orig_summary

    print('\n== 3) 大模型异常 -> 自动降级 ==')
    def _boom(*a, **k):
        raise llm.LLMError('mock 网络错误')
    api_v1.llm.chat_json = _boom
    out = api_v1._analysis_for(DET, 'INSP-TEST', 'pending')
    check(out.get('source') == 'rule_fallback', 'analysis 异常降级')
    check('降级' in out.get('reason', ''), '降级原因可见')
    answer, refs, source = api_v1._answer_question('batch', 'B-1', '怎么办？')
    check(source == 'rule_fallback', 'chat 异常降级')

    print('\n== 4) /api/llm/info 状态 ==')
    info = llm.info()
    check('provider' in info and 'model' in info and 'configured' in info, 'llm/info 字段齐全')
    check('api_key' not in str(info).lower().replace('configured', ''), '不泄露 Key')

    real_key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if real_key and not real_key.startswith('sk-your'):
        print('\n== 5) 真实 DeepSeek 调用（检测到已配置 Key） ==')
        try:
            res = llm.chat_json('你是助手，只输出 JSON。', '请输出 JSON：{"ok": true, "msg": "hello"}', max_tokens=50)
            check(isinstance(res.get('data'), dict), '真实调用返回 JSON')
            print('  模型:', res.get('model'), '| 时延:', res.get('latency_ms'), 'ms')
        except Exception as e:  # noqa: BLE001
            check(False, '真实调用失败: %r' % e)
    elif llm.provider() == 'local':
        print('\n== 5) 真实本地大模型调用（无需 Key） ==')
        try:
            res = llm.chat_json('你是助手，只输出 JSON。', '请输出 JSON：{"ok": true, "msg": "hello"}', max_tokens=60)
            check(isinstance(res.get('data'), dict), '本地真实调用返回 JSON')
            print('  模型:', res.get('model'), '| 设备:', res.get('device'), '| 时延:', res.get('latency_ms'), 'ms')
        except Exception as e:  # noqa: BLE001
            check(False, '本地真实调用失败: %r' % e)
    else:
        print('\n== 5) 真实大模型调用：跳过（未配置 Key，且本地模型未就绪） ==')

    api_v1.llm.available = orig_available
    api_v1.llm.chat_json = orig_chat
    api_v1.llm.source_name = orig_source

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
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
