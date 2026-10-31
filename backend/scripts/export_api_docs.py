# -*- coding: utf-8 -*-
"""Export OpenAPI without touching production storage or calling model services.

python scripts/export_api_docs.py
python scripts/export_api_docs.py --out docs/openapi.json
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs' / 'openapi.json')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix='steelscan-openapi-') as directory, patch.dict(os.environ, {
        'STEELSCAN_STORAGE_DIR': directory, 'STEELSCAN_DB': str(Path(directory) / 'schema.db'),
        'STEELSCAN_API_KEY': '', 'MODELSCOPE_API_TOKEN': '', 'DETECTOR_PROVIDER': 'modelscope',
        'DEEPSEEK_API_KEY': '', 'OPENAI_API_KEY': '', 'LLM_PROVIDER': 'deepseek',
        'LOCAL_LLM_MODEL': 'models/not-installed',
    }):
        from server import APP_VERSION, app
        spec = app.openapi()
        spec['info']['version'] = APP_VERSION
        spec['info']['description'] = (
            'SteelScan 轻量业务 API：YOLO26n@640 魔搭云检测、同步HTTP、完整复核与Markdown报告。'
            '多数响应尚未声明response_model，完整响应结构另见docs/api_samples；OpenAPI导出不验证云连通性。')
        review = spec['components']['schemas']['ReviewRequest']
        assert 'base_version' in review['required']
        assert review['properties']['base_version']['minimum'] == 0
        assert '/api/inspections/{inspection_id}/review' in spec['paths']
        encoded = json.dumps(spec, ensure_ascii=False, indent=2) + '\n'
        for private_path in (str(ROOT), str(Path.home()), directory):
            assert private_path not in encoded and json.dumps(private_path)[1:-1] not in encoded
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding='utf-8')
    print('Exported OpenAPI:', args.out, '(%d paths; no inference calls)' % len(spec['paths']))


if __name__ == '__main__':
    main()
