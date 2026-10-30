# -*- coding: utf-8 -*-
"""导出数据划分清单（团队契约交付物：类别映射 + 固定划分）。

输出：docs/data_split_manifest.json
用法：python scripts/export_split_manifest.py
"""
import json
import os

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(DEV, 'data', 'neu_det')
OUT = os.path.join(DEV, 'docs', 'data_split_manifest.json')


def main():
    manifest = {
        'dataset': 'NEU-DET（东北大学热轧带钢表面缺陷数据库，检测版）',
        'source': 'https://faculty.neu.edu.cn/songkc/en/zdylm/263265/list/index.htm',
        'license_note': '学术研究使用；引用 Song & Yan 2013、He et al. 2020',
        'image_size': [200, 200],
        'num_images': 1800,
        'num_boxes': 4189,
        'split_ratio': [0.70, 0.15, 0.15],
        'seed': 0,
        'split_policy': '按原图分层（每类 300 张 → 210/45/45），同一原图不跨集合',
        'raw_model_classes': ['rolled-in_scale', 'patches', 'crazing', 'pitted_surface', 'inclusion', 'scratches'],
        'contract_classes': [
            {'class_id': 0, 'class_name': 'crazing', 'class_cn': '龟裂 / 网状裂纹'},
            {'class_id': 1, 'class_name': 'inclusion', 'class_cn': '夹杂'},
            {'class_id': 2, 'class_name': 'patches', 'class_cn': '斑块'},
            {'class_id': 3, 'class_name': 'pitted_surface', 'class_cn': '麻点表面'},
            {'class_id': 4, 'class_name': 'rolled-in_scale', 'class_cn': '轧入氧化皮'},
            {'class_id': 5, 'class_name': 'scratches', 'class_cn': '划痕'},
        ],
        'class_mapping': [
            {'raw_index': 0, 'raw_name': 'rolled-in_scale', 'contract_class_id': 4},
            {'raw_index': 1, 'raw_name': 'patches', 'contract_class_id': 2},
            {'raw_index': 2, 'raw_name': 'crazing', 'contract_class_id': 0},
            {'raw_index': 3, 'raw_name': 'pitted_surface', 'contract_class_id': 3},
            {'raw_index': 4, 'raw_name': 'inclusion', 'contract_class_id': 1},
            {'raw_index': 5, 'raw_name': 'scratches', 'contract_class_id': 5},
        ],
        'splits': {},
    }
    for split in ('train', 'val', 'test'):
        img_dir = os.path.join(DATA_DIR, 'images', split)
        if os.path.isdir(img_dir):
            files = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')))
            manifest['splits'][split] = {'count': len(files), 'files': files}
        else:
            manifest['splits'][split] = {'count': 0, 'files': []}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print('已导出:', OUT)
    for k, v in manifest['splits'].items():
        print('  %s: %d 张' % (k, v['count']))


if __name__ == '__main__':
    main()
