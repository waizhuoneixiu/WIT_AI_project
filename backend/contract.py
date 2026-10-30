# -*- coding: utf-8 -*-
"""团队共同接口约定（见仓库 docs/plans/04-shared-contract.md）。

模型训练时的类别顺序是 RAW_CLASSES；对外 API 统一使用 CONTRACT_CLASSES 的 class_id，
两者通过 contract_class() 转换，避免 App/报告/模型输出编号不一致。
"""

# 团队约定的对外类别编号（04-shared-contract.md）
CONTRACT_CLASSES = [
    {'class_id': 0, 'class_name': 'crazing', 'class_cn': '龟裂 / 网状裂纹'},
    {'class_id': 1, 'class_name': 'inclusion', 'class_cn': '夹杂'},
    {'class_id': 2, 'class_name': 'patches', 'class_cn': '斑块'},
    {'class_id': 3, 'class_name': 'pitted_surface', 'class_cn': '麻点表面'},
    {'class_id': 4, 'class_name': 'rolled-in_scale', 'class_cn': '轧入氧化皮'},
    {'class_id': 5, 'class_name': 'scratches', 'class_cn': '划痕'},
]

# 模型训练时的原始类别顺序（NEU-DET，ultralytics data.yaml 顺序）
RAW_CLASSES = ['rolled-in_scale', 'patches', 'crazing', 'pitted_surface', 'inclusion', 'scratches']

_BY_NAME = {c['class_name']: c for c in CONTRACT_CLASSES}
_BY_ID = {c['class_id']: c for c in CONTRACT_CLASSES}


def contract_class(class_name):
    """原始类别名 -> 契约类别 dict（未知类别原样返回）。"""
    c = _BY_NAME.get(class_name)
    if c:
        return dict(c)
    return {'class_id': -1, 'class_name': class_name, 'class_cn': class_name}


def class_by_id(class_id):
    return dict(_BY_ID[int(class_id)])


def classes():
    """契约类别列表（用于 /classes 与文档）。"""
    return [dict(c) for c in CONTRACT_CLASSES]
