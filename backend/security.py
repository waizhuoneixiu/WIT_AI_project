# -*- coding: utf-8 -*-
"""API Key 鉴权依赖（服务端设置 STEELSCAN_API_KEY 后生效）。"""
from hmac import compare_digest

from fastapi import Header, HTTPException

import config


def verify_api_key(x_api_key: str = Header(default=None, description='API Key（服务端设置 STEELSCAN_API_KEY 后必填）')):
    expected = config.API_KEY
    if expected and not compare_digest((x_api_key or '').encode('utf-8'), expected.encode('utf-8')):
        raise HTTPException(status_code=401, detail='无效或缺失 API Key（请求头 X-API-Key）')
