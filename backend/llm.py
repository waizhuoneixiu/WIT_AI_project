# -*- coding: utf-8 -*-
"""大模型客户端：DeepSeek API / 本地 DeepSeek-R1（transformers）/ 自动降级。

选择规则（LLM_PROVIDER）：
    auto       : 有 DEEPSEEK_API_KEY -> deepseek；否则若本地模型存在 -> local
    deepseek（默认）: DeepSeek 云 API（需要 Key）
    local       : 强制本地 transformers 模型（无需 Key，离线可用）

未配置/失败时由上层（api_v1）自动降级到规则模板。
Key 只从环境变量 / .env 读取，不写死在代码里。
"""
import json
import os
import re
import threading
import time

import config

config.load_dotenv_if_present()

DEV = os.path.dirname(os.path.abspath(__file__))

LLM_PROVIDER = os.environ.get('LLM_PROVIDER', config.LLM_PROVIDER).strip().lower() or 'deepseek'
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '40'))
LLM_MAX_RETRIES = int(os.environ.get('LLM_MAX_RETRIES', '2'))

LOCAL_LLM_MODEL = os.environ.get('LOCAL_LLM_MODEL', '').strip() or os.path.join(
    DEV, 'models', 'DeepSeek-R1-Distill-Qwen-1.5B')
LOCAL_LLM_DEVICE = os.environ.get('LOCAL_LLM_DEVICE', 'cuda').strip().lower() or 'cuda'
LOCAL_LLM_MAX_NEW_TOKENS = int(os.environ.get('LOCAL_LLM_MAX_NEW_TOKENS', '2000'))

_lock = threading.Lock()
_local = {'model': None, 'tokenizer': None, 'device': None}


class LLMError(Exception):
    """大模型调用失败（上层应降级）。"""


def _local_ready():
    return os.path.exists(os.path.join(LOCAL_LLM_MODEL, 'config.json'))


def provider():
    """返回当前实际可用的 provider：'deepseek' / 'local' / None。"""
    if LLM_PROVIDER == 'deepseek':
        return 'deepseek' if DEEPSEEK_API_KEY else None
    if LLM_PROVIDER == 'local':
        return 'local' if _local_ready() else None
    # auto
    if DEEPSEEK_API_KEY:
        return 'deepseek'
    if _local_ready():
        return 'local'
    return None


def available():
    return provider() is not None


def source_name():
    """写入 analysis/chat 的 source 字段。"""
    p = provider()
    if p == 'deepseek':
        return 'deepseek'
    if p == 'local':
        return 'local-deepseek'
    return 'rule_fallback'


def info():
    p = provider()
    if p == 'deepseek':
        mode, model = 'deepseek-api', DEEPSEEK_MODEL
    elif p == 'local':
        mode, model = 'local-transformers', os.path.basename(LOCAL_LLM_MODEL.rstrip('\\/'))
    else:
        mode = 'rule-fallback'
        model = LOCAL_LLM_MODEL if LLM_PROVIDER == 'local' else DEEPSEEK_MODEL
    return {
        'provider': p or 'none',
        'mode': mode,
        'model': model,
        'configured': p is not None,
        'source': source_name(),
        'deepseek_configured': bool(DEEPSEEK_API_KEY),
        'local_model_path': LOCAL_LLM_MODEL,
        'local_model_ready': _local_ready(),
        'base_url': DEEPSEEK_BASE_URL,
        'timeout_s': LLM_TIMEOUT,
    }


# ---------------------------------------------------------------------------
# DeepSeek 云 API
# ---------------------------------------------------------------------------
def _deepseek_client():
    from openai import OpenAI
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL,
                  timeout=LLM_TIMEOUT, max_retries=0)


def _deepseek_once(system_prompt, user_prompt, temperature=0.2, max_tokens=1400):
    client = _deepseek_client()
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{'role': 'system', 'content': system_prompt},
                      {'role': 'user', 'content': user_prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={'type': 'json_object'},
        )
    except Exception as e:  # noqa: BLE001
        raise LLMError('DeepSeek 请求失败: %s' % str(e)[:200])
    latency_ms = (time.perf_counter() - t0) * 1000.0
    try:
        content = resp.choices[0].message.content or ''
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError('返回不是 JSON 对象')
    except Exception as e:  # noqa: BLE001
        raise LLMError('DeepSeek 返回解析失败: %s' % str(e)[:120])
    usage = getattr(resp, 'usage', None)
    tokens = {}
    if usage is not None:
        tokens = {'prompt_tokens': getattr(usage, 'prompt_tokens', None),
                  'completion_tokens': getattr(usage, 'completion_tokens', None),
                  'total_tokens': getattr(usage, 'total_tokens', None)}
    return {'data': data, 'model': DEEPSEEK_MODEL, 'latency_ms': round(latency_ms, 2), 'tokens': tokens}


# ---------------------------------------------------------------------------
# 本地 transformers 模型（DeepSeek-R1-Distill-Qwen-1.5B 等）
# ---------------------------------------------------------------------------
def _load_local():
    global _local
    if _local['model'] is not None:
        return
    with _lock:
        if _local['model'] is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as e:  # noqa: BLE001
            raise LLMError('本地模型依赖缺失（transformers/torch）: %s' % str(e)[:160])
        if not _local_ready():
            raise LLMError('本地模型不存在: %s（先运行 scripts/download_local_llm.py）' % LOCAL_LLM_MODEL)
        use_cuda = LOCAL_LLM_DEVICE.startswith('cuda') and torch.cuda.is_available()
        dtype = torch.float16 if use_cuda else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(LOCAL_LLM_MODEL, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            LOCAL_LLM_MODEL, local_files_only=True, trust_remote_code=False, dtype=dtype)
        device = 'cuda' if use_cuda else 'cpu'
        model.to(device)
        model.eval()
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        _local.update({'model': model, 'tokenizer': tokenizer, 'device': device})
        print('[llm] 本地模型已加载: %s (%s)' % (LOCAL_LLM_MODEL, device), flush=True)


def _extract_json(text):
    """从模型输出中提取 JSON 对象（容忍思考过程、代码块、前后废话）。"""
    text = (text or '').strip()
    # DeepSeek-R1 蒸馏模型可能先输出 思考过程，取最后一段之后的内容
    if '<｜end▁of▁thinking｜>' in text:
        text = text.rsplit('<｜end▁of▁thinking｜>', 1)[-1].strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:  # noqa: BLE001
            pass
    raise LLMError('模型输出不是合法 JSON: %s' % text[:120])


def _local_once(system_prompt, user_prompt, temperature=0.2, max_tokens=700, retry_hint=False):
    _load_local()
    import torch
    model = _local['model']
    tokenizer = _local['tokenizer']
    device = _local['device']
    t0 = time.perf_counter()
    suffix = ('\n\n请直接输出最终 JSON 对象：以 { 开头、以 } 结尾，'
              '不要输出思考过程、解释或 Markdown 代码块。')
    if retry_hint:
        suffix = ('\n\n注意：只允许输出一个合法的 JSON 对象本身，'
                  '不要输出任何其他文字、思考过程或代码块。')
    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt + suffix}]
    try:
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors='pt').to(device)
        max_new = min(max(int(max_tokens), LOCAL_LLM_MAX_NEW_TOKENS), 2048)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new,
                do_sample=temperature > 0,
                temperature=max(temperature, 0.01),
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                repetition_penalty=1.05,
            )
        gen_ids = out[0][inputs['input_ids'].shape[1]:]
        content = tokenizer.decode(gen_ids, skip_special_tokens=True)
    except Exception as e:  # noqa: BLE001
        raise LLMError('本地模型推理失败: %s' % str(e)[:200])
    latency_ms = (time.perf_counter() - t0) * 1000.0
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise LLMError('本地模型返回不是 JSON 对象')
    return {'data': data, 'model': os.path.basename(LOCAL_LLM_MODEL.rstrip('\\/')),
            'latency_ms': round(latency_ms, 2),
            'tokens': {'completion_tokens': int(len(gen_ids)) if hasattr(gen_ids, '__len__') else None},
            'device': device, 'max_new_tokens': max_new}


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
def chat_json(system_prompt, user_prompt, temperature=0.2, max_tokens=1400):
    """统一 JSON 输出调用；失败抛 LLMError（上层降级）。"""
    p = provider()
    if p == 'local':
        last = None
        for attempt in range(2):
            try:
                return _local_once(system_prompt, user_prompt, temperature, max_tokens,
                                   retry_hint=attempt > 0)
            except LLMError as e:  # noqa: PERF203
                last = e
        raise last or LLMError('本地模型调用失败')
    if p == 'deepseek':
        last = None
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                return _deepseek_once(system_prompt, user_prompt, temperature, max_tokens)
            except LLMError as e:  # noqa: PERF203
                last = e
                if attempt < LLM_MAX_RETRIES:
                    time.sleep(1.0 * (attempt + 1))
        raise last or LLMError('未知错误')
    raise LLMError('未配置大模型（DEEPSEEK_API_KEY 为空，本地模型不存在）')
