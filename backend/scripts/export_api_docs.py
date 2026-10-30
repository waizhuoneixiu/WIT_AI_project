# -*- coding: utf-8 -*-
"""导出 FastAPI 的 OpenAPI 规范到 docs/openapi.json（供前端/队友生成客户端或调试）。

用法：
    python scripts/export_api_docs.py
    python scripts/export_api_docs.py --out "D:\\...\\AIvision1\\docs\\openapi.json"
"""
import argparse
import json
import os
import sys

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEV not in sys.path:
    sys.path.insert(0, DEV)

from server import APP_VERSION, app  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DEV, 'docs', 'openapi.json'))
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    spec = app.openapi()
    spec['info']['version'] = APP_VERSION
    spec['info']['description'] = 'SteelScan 热轧带钢表面缺陷检测后端 API（YOLO26n @640）'
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print('OpenAPI 已导出:', args.out)
    print('接口列表:')
    for path, methods in spec.get('paths', {}).items():
        for method in methods:
            print('  %-6s %s' % (method.upper(), path))


if __name__ == '__main__':
    main()
