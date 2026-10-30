# -*- coding: utf-8 -*-
"""DeepSeek 大模型客户端（OpenAI 兼容接口）。

- 仅在配置 DEEPSEEK_API_KEY 时启用；未配置/超时/报错时由上层自动降级到规则模板。
- 使用 JSON 输出模式，返回 dict；解析失败抛 LLMError 由上层降级。
- Key 只从环境变量 / .env 读取，不写死在代码里。
"""
import json
import os
import time

import config

config.load_dotenv_if_present()

LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'deepseek')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '40'))
LLM_MAX_RETRIES = int(os.environ.get('LLM_MAX_RETRIES', '2'))


class LLMError(Exception):
    """大模型调用失败（上层应降级）。"""


def available():
    return LLM_PROVIDER == 'deepseek' and bool(DEEPSEEK_API_KEY)


def info():
    return {
        'provider': LLM_PROVIDER,
        'model': DEEPSEEK_MODEL,
        'configured': available(),
        'base_url': DEEPSEEK_BASE_URL,
        'timeout_s': LLM_TIMEOUT,
    }


def _client():
    from openai import OpenAI
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL,
                  timeout=LLM_TIMEOUT, max_retries=0)


def _chat_json_once(system_prompt, user_prompt, temperature=0.2, max_tokens=1400):
    client = _client()
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={'type': 'json_object'},
        )
    except Exception as e:  # noqa: BLE001
        raise LLMError('DeepSeek 请求失败: %s' % str(e)[:200])
    latency_ms = (time.perf_counter() - t0) * 1000.0
    content = ''
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
        tokens = {
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'completion_tokens': getattr(usage, 'completion_tokens', None),
            'total_tokens': getattr(usage, 'total_tokens', None),
        }
    return {
        'data': data,
        'model': DEEPSEEK_MODEL,
        'latency_ms': round(latency_ms, 2),
        'tokens': tokens,
    }


def chat_json(system_prompt, user_prompt, temperature=0.2, max_tokens=1400):
    """带重试的 JSON 输出调用；失败抛 LLMError。"""
    if not available():
        raise LLMError('未配置 DEEPSEEK_API_KEY（或 LLM_PROVIDER 不是 deepseek）')
    last = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            return _chat_json_once(system_prompt, user_prompt, temperature, max_tokens)
        except LLMError as e:  # noqa: PERF203
            last = e
            if attempt < LLM_MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))
    raise last or LLMError('未知错误')
