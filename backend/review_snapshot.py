"""Rebuild a review from immutable model detections and a complete correction set."""
import math
import uuid

import contract


def apply_corrections(detections, corrections, width, height):
    originals = {d['detection_id']: d for d in detections}
    effective = {key: dict(d, source='model') for key, d in originals.items()}
    normalized, seen = [], set()
    if not isinstance(corrections, list):
        raise ValueError('corrections 必须是数组')
    for item in corrections:
        if not isinstance(item, dict):
            raise ValueError('每条修正必须是对象')
        op = item.get('op', 'update')
        detection_id = item.get('detection_id')
        if not isinstance(detection_id, str) or not detection_id or detection_id in seen:
            raise ValueError('detection_id 缺失或重复')
        seen.add(detection_id)
        if op not in ('add', 'update', 'delete'):
            raise ValueError('op 仅支持 add/update/delete')
        allowed = {'op', 'detection_id'} if op == 'delete' else {'op', 'detection_id', 'class_id', 'bbox_xyxy'}
        if set(item) - allowed:
            raise ValueError('修正包含不支持的字段')
        if op == 'add':
            try:
                uuid.UUID(detection_id)
            except ValueError:
                raise ValueError('人工新增框 detection_id 必须是 UUID') from None
            if detection_id in originals:
                raise ValueError('人工新增框不能复用模型框编号')
            original = {}
        else:
            if detection_id not in originals:
                raise ValueError('修正目标不属于本记录的原模型框')
            original = originals[detection_id]
        if op == 'delete':
            effective.pop(detection_id)
            normalized.append({'op': op, 'detection_id': detection_id})
            continue
        if op == 'update' and not ({'class_id', 'bbox_xyxy'} & item.keys()):
            raise ValueError('update 必须提供类别或坐标')
        class_id = item.get('class_id', original.get('class_id'))
        if type(class_id) is not int or class_id not in range(len(contract.CONTRACT_CLASSES)):
            raise ValueError('class_id 必须是 0 至 5 的整数')
        bbox = item.get('bbox_xyxy', original.get('bbox_xyxy'))
        if (not isinstance(bbox, list) or len(bbox) != 4
                or any(type(v) not in (int, float) or (type(v) is float and not math.isfinite(v)) for v in bbox)):
            raise ValueError('bbox_xyxy 必须包含四个有限数值')
        x1, y1, x2, y2 = bbox
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError('边界框必须位于原图内且宽高大于零')
        normalized.append({'op': op, 'detection_id': detection_id,
                           'class_id': class_id, 'bbox_xyxy': list(bbox)})
        effective[detection_id] = {
            'detection_id': detection_id, **contract.class_by_id(class_id),
            'bbox_xyxy': list(bbox), 'score': None, 'source': 'manual',
        }
    return normalized, list(effective.values())
