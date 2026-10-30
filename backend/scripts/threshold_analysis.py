# -*- coding: utf-8 -*-
"""业务阈值分析：在 test 集上扫描 conf，计算 Precision/Recall/F1，选最佳阈值。

用法：
    python scripts/threshold_analysis.py --weights runs/n320/weights/best.pt --imgsz 320
输出：runs/threshold_<实验名>_<imgsz>.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
sys.path.insert(0, DEV)

from ultralytics import YOLO  # noqa: E402

from config import DATA_DIR  # noqa: E402

IOU_THR = 0.5
CONFS = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05 ~ 0.95


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def load_gt(label_path, w, h):
    gts = []
    if not os.path.exists(label_path):
        return gts
    with open(label_path, encoding='utf-8') as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5:
                continue
            cls = int(float(parts[0]))
            cx, cy, bw, bh = map(float, parts[1:5])
            x1, y1 = (cx - bw / 2) * w, (cy - bh / 2) * h
            x2, y2 = (cx + bw / 2) * w, (cy + bh / 2) * h
            gts.append({'cls': cls, 'box': [x1, y1, x2, y2]})
    return gts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', required=True)
    ap.add_argument('--imgsz', type=int, default=320)
    ap.add_argument('--device', default='0')
    args = ap.parse_args()

    model = YOLO(args.weights)
    img_dir = os.path.join(DATA_DIR, 'images', 'test')
    lbl_dir = os.path.join(DATA_DIR, 'labels', 'test')
    files = sorted(glob.glob(os.path.join(img_dir, '*.*')))
    preds = []
    for p in files:
        r = model.predict(source=p, conf=0.001, imgsz=args.imgsz, device=args.device, verbose=False)[0]
        h, w = r.orig_shape[:2]
        gt = load_gt(os.path.join(lbl_dir, os.path.splitext(os.path.basename(p))[0] + '.txt'), w, h)
        boxes = []
        if r.boxes is not None and len(r.boxes):
            for c, conf, xyxy in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
                boxes.append({'cls': int(c), 'conf': float(conf), 'box': [float(v) for v in xyxy]})
        preds.append({'gt': gt, 'pred': boxes})

    rows = []
    for conf_thr in CONFS:
        tp = fp = fn = 0
        for item in preds:
            used = [False] * len(item['gt'])
            for pr in item['pred']:
                if pr['conf'] < conf_thr:
                    continue
                best_iou, best_j = 0.0, -1
                for j, g in enumerate(item['gt']):
                    if used[j] or g['cls'] != pr['cls']:
                        continue
                    v = iou(pr['box'], g['box'])
                    if v > best_iou:
                        best_iou, best_j = v, j
                if best_iou >= IOU_THR and best_j >= 0:
                    tp += 1
                    used[best_j] = True
                else:
                    fp += 1
            fn += used.count(False) if len(item['gt']) else 0
            if not item['gt']:
                fn += sum(1 for pr in item['pred'] if pr['conf'] >= conf_thr)
                fn -= fp  # 回退（正常 test 集无背景图，不影响）
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append({'conf': conf_thr, 'tp': tp, 'fp': fp, 'fn': fn,
                     'precision': round(prec, 4), 'recall': round(rec, 4), 'f1': round(f1, 4)})

    best_f1 = max(rows, key=lambda x: x['f1'])
    recall95 = next((r for r in rows if r['recall'] < 0.95), rows[-1])
    report = {
        'weights': args.weights,
        'imgsz': args.imgsz,
        'images': len(files),
        'iou_threshold': IOU_THR,
        'best_f1': best_f1,
        'recommended_conf': best_f1['conf'],
        'curve': rows,
    }
    name = os.path.basename(os.path.dirname(os.path.dirname(args.weights)))
    out = os.path.join(DEV, 'runs', 'threshold_%s_%d.json' % (name, args.imgsz))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('best F1:', json.dumps(best_f1, ensure_ascii=False))
    print('curve:')
    for r in rows:
        print('  conf=%.2f  P=%.3f R=%.3f F1=%.3f' % (r['conf'], r['precision'], r['recall'], r['f1']))
    print('saved:', out)


if __name__ == '__main__':
    main()
