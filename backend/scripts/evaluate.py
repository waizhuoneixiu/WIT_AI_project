# -*- coding: utf-8 -*-
"""模型评测：test 集 mAP / 每类 AP / 召回 / 漏检率 / 过杀率 / 时延。"""
import argparse
import json
import os
import sys
import time

import numpy as np

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
sys.path.insert(0, DEV)

from ultralytics import YOLO  # noqa: E402

from config import CLASSES, CLASSES_CN, DATA_YAML, RUNS_DIR  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', required=True)
    ap.add_argument('--imgsz', type=int, default=320)
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--device', default='0')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    model = YOLO(args.weights)
    data_root = os.path.dirname(DATA_YAML)
    test_dir = os.path.join(data_root, 'images', 'test')
    img_files = sorted(os.path.join(test_dir, f) for f in os.listdir(test_dir) if f.lower().endswith(('.jpg', '.jpeg', '.bmp', '.png')))

    # 1) 官方 val 指标（test split）
    metrics = model.val(data=DATA_YAML, split='test', imgsz=args.imgsz, conf=0.001, iou=0.5,
                        device=args.device, verbose=False, plots=True)
    rd = metrics.results_dict
    per_class = {}
    try:
        idx = list(range(len(CLASSES)))
        ap50 = metrics.box.ap50
        ap = metrics.box.ap
        mp = metrics.box.p
        mr = metrics.box.r
        for i in idx:
            per_class[CLASSES[i]] = {
                'AP50': round(float(ap50[i]), 4),
                'AP50-95': round(float(ap[i]), 4),
                'precision': round(float(mp[i]), 4),
                'recall': round(float(mr[i]), 4),
            }
    except Exception as e:
        print('per-class err:', e)

    # 2) 业务阈值下的召回/漏检率/过杀率（把 test 当"全为 NG"的已知缺陷集）
    #    注：NEU-DET test 全部含缺陷，因此召回=检出图的比率；漏检率=1-召回。
    detect_hit = 0
    low_conf_files = []
    latencies = []
    pred_boxes = 0
    for p in img_files:
        r = model.predict(source=p, conf=args.conf, imgsz=args.imgsz, device=args.device, verbose=False)[0]
        n = 0 if r.boxes is None else len(r.boxes)
        pred_boxes += n
        latencies.append(r.speed.get('inference', 0.0) if isinstance(r.speed, dict) else 0.0)
        if n > 0:
            detect_hit += 1
        else:
            low_conf_files.append(os.path.basename(p))
    recall_img = detect_hit / max(1, len(img_files))
    report = {
        'weights': args.weights,
        'imgsz': args.imgsz,
        'test_images': len(img_files),
        'mAP50': round(float(rd.get('metrics/mAP50(B)', 0)), 4),
        'mAP50-95': round(float(rd.get('metrics/mAP50-95(B)', 0)), 4),
        'precision': round(float(rd.get('metrics/precision(B)', 0)), 4),
        'recall': round(float(rd.get('metrics/recall(B)', 0)), 4),
        'per_class': per_class,
        'image_hit_rate': round(recall_img, 4),
        'miss_rate': round(1 - recall_img, 4),
        'missed_images': low_conf_files[:20],
        'avg_boxes_per_image': round(pred_boxes / max(1, len(img_files)), 3),
        'avg_inference_ms': round(float(np.mean(latencies)), 2) if latencies else 0,
        'fps_est': round(1000.0 / float(np.mean(latencies)), 1) if latencies else 0,
    }
    out = args.out or os.path.join(RUNS_DIR, 'eval_%s_%d.json' % (os.path.basename(os.path.dirname(os.path.dirname(args.weights))), args.imgsz))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('saved:', out)


if __name__ == '__main__':
    main()
