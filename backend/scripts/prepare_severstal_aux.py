# -*- coding: utf-8 -*-
"""把 ModelScope Severstal 数据集（Voxel51 版）转成 YOLO 二分类检测数据集。

用法：python scripts/prepare_severstal_aux.py
输出：data/severstal_yolo/{images,labels}/{train,val} + data.yaml
"""
import base64
import io
import json
import os
import random
import shutil
import zlib

import cv2
import numpy as np

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
SRC = os.path.join(PROJ, 'data', 'severstal_ms')
OUT = os.path.join(PROJ, 'data', 'severstal_yolo')
MIN_AREA = 30


def decode_mask(gt):
    raw = zlib.decompress(base64.b64decode(gt['mask']['$binary']['base64']))
    return np.load(io.BytesIO(raw))


def main():
    samples = json.load(open(os.path.join(SRC, 'samples.json'), encoding='utf-8'))['samples']
    by_path = {}
    for s in samples:
        fp = s.get('filepath')
        if fp:
            by_path[fp] = s

    img_root = os.path.join(SRC, 'data')
    images = []
    for root, _, files in os.walk(img_root):
        for fn in files:
            if fn.lower().endswith('.jpg'):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, SRC).replace('\\', '/')
                images.append((full, rel))
    print('available images:', len(images))

    records = []
    matched = 0
    defect_imgs = 0
    boxes = 0
    for full, rel in images:
        s = by_path.get(rel)
        if s is None:
            continue
        matched += 1
        labels = []
        gt = s.get('ground_truth')
        if isinstance(gt, dict) and 'mask' in gt:
            try:
                arr = decode_mask(gt)
                mask = (arr > 0).astype(np.uint8)
                n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
                h, w = mask.shape
                for st in stats[1:]:
                    x, y, bw, bh, area = [int(v) for v in st]
                    if area < MIN_AREA or bw <= 1 or bh <= 1:
                        continue
                    cx = (x + bw / 2.0) / w
                    cy = (y + bh / 2.0) / h
                    nw = bw / w
                    nh = bh / h
                    if nw <= 0 or nh <= 0:
                        continue
                    labels.append([0, min(max(cx, 0), 1), min(max(cy, 0), 1),
                                   min(max(nw, 0), 1), min(max(nh, 0), 1)])
            except Exception:  # noqa: BLE001
                pass
        if labels:
            defect_imgs += 1
            boxes += len(labels)
        records.append({'full': full, 'rel': rel, 'labels': labels,
                        'has_defect': bool(labels)})

    print('matched samples:', matched, '| defect images:', defect_imgs, '| boxes:', boxes)

    # 9:1 划分，按有/无缺陷分层
    rng = random.Random(0)
    pos = [r for r in records if r['has_defect']]
    neg = [r for r in records if not r['has_defect']]
    rng.shuffle(pos)
    rng.shuffle(neg)
    n_val_pos = max(1, int(len(pos) * 0.1))
    n_val_neg = max(1, int(len(neg) * 0.1))
    val = pos[:n_val_pos] + neg[:n_val_neg]
    train = pos[n_val_pos:] + neg[n_val_neg:]
    rng.shuffle(train)
    rng.shuffle(val)
    print('train:', len(train), '| val:', len(val))

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for split in ('train', 'val'):
        os.makedirs(os.path.join(OUT, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(OUT, 'labels', split), exist_ok=True)
    for split, recs in (('train', train), ('val', val)):
        for r in recs:
            dst_img = os.path.join(OUT, 'images', split, os.path.basename(r['full']))
            try:
                os.link(r['full'], dst_img)
            except Exception:  # noqa: BLE001
                shutil.copy2(r['full'], dst_img)
            lab_path = os.path.join(OUT, 'labels', split,
                                    os.path.splitext(os.path.basename(r['full']))[0] + '.txt')
            with open(lab_path, 'w', encoding='utf-8') as f:
                for c, cx, cy, w, h in r['labels']:
                    f.write('%d %.6f %.6f %.6f %.6f\n' % (c, cx, cy, w, h))

    yaml = os.path.join(OUT, 'data.yaml')
    with open(yaml, 'w', encoding='utf-8') as f:
        f.write('path: %s\n' % OUT.replace('\\', '/'))
        f.write('train: images/train\nval: images/val\n')
        f.write('nc: 1\nnames: [defect]\n')
    print('saved:', yaml)
    print('train imgs:', len(os.listdir(os.path.join(OUT, 'images', 'train'))),
          '| val imgs:', len(os.listdir(os.path.join(OUT, 'images', 'val'))))


if __name__ == '__main__':
    main()
