# -*- coding: utf-8 -*-
"""本地大模型真实调用冒烟测试（无需 Key）。

用法（模型默认在 models/DeepSeek-R1-Distill-Qwen-1.5B）：
    python scripts/test_local_llm.py
可通过环境变量 LOCAL_LLM_MODEL 指定模型目录、LOCAL_LLM_DEVICE=cpu 强制 CPU。
"""
import json
import os
import sys
import time

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEV)

import llm  # noqa: E402


def main():
    info = llm.info()
    print('llm info:', json.dumps(info, ensure_ascii=False))
    if not llm.available():
        print('\n本地模型未就绪：请先运行 python scripts/download_local_llm.py')
        return 1
    print('\n== 加载模型并真实推理 ==')
    t0 = time.time()
    result = llm.chat_json(
        '你是热轧带钢表面质检助手，只输出严格 JSON（不要 Markdown）。',
        '检测到 2 处 patches（斑块）缺陷，置信度 0.88 和 0.81，图片 200x200。\n'
        '请输出 JSON：{"facts": ["..."], "references": ["..."], "hypotheses": ["..."], '
        '"recheck_steps": ["..."], "missing_information": ["..."]}',
        max_tokens=220,
    )
    elapsed = time.time() - t0
    data = result.get('data', {})
    print('模型:', result.get('model'), '| 设备:', result.get('device'),
          '| 推理时延:', result.get('latency_ms'), 'ms | 端到端:', round(elapsed, 2), 's')
    print('字段:', list(data.keys()))
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
    required = ('facts', 'references', 'hypotheses', 'recheck_steps', 'missing_information')
    missing = [k for k in required if k not in data]
    if missing:
        print('\n[FAIL] 缺少字段:', missing)
        return 1
    print('\n全部通过 ✔')
    return 0


if __name__ == '__main__':
    sys.exit(main())
