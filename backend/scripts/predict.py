# -*- coding: utf-8 -*-
"""命令行推理（后端自测/联调用）。

用法：
    python scripts/predict.py --image data/neu_det/images/test/crazing_1.jpg
    python scripts/predict.py --dir data/neu_det/images/test --limit 10
    python scripts/predict.py --image xxx.jpg --save-dir output/  # 保存带框标注图
"""
import argparse
import json
import os
import sys

import cv2

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEV not in sys.path:
    sys.path.insert(0, DEV)

import config  # noqa: E402
config.load_dotenv_if_present()

from detector import DefectDetector, resolve_weights  # noqa: E402


def draw(img, result):
    out = img.copy()
    for d in result['defects']:
        x1, y1, x2, y2 = [int(v) for v in d['bbox_xyxy']]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 1)
        label = '%s %.2f' % (d['class_name'], d['confidence'])
        cv2.putText(out, label, (x1, max(10, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', default=None)
    ap.add_argument('--image', default='')
    ap.add_argument('--dir', default='')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--imgsz', type=int, default=config.DEFAULT_IMGSZ)
    ap.add_argument('--device', default=str(config.DEFAULT_DEVICE))
    ap.add_argument('--save-dir', default='')
    args = ap.parse_args()

    det = DefectDetector(weights=args.weights or resolve_weights(), imgsz=args.imgsz, conf=args.conf, device=args.device)
    files = []
    if args.image:
        files = [args.image]
    elif args.dir:
        files = [os.path.join(args.dir, f) for f in sorted(os.listdir(args.dir))
                 if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]
        if args.limit:
            files = files[:args.limit]
    if not files:
        raise SystemExit('请用 --image 或 --dir 指定输入')

    for p in files:
        img = cv2.imread(p)
        if img is None:
            print('skip unreadable:', p)
            continue
        r = det.detect(img)
        r['filename'] = os.path.basename(p)
        print(json.dumps(r, ensure_ascii=False))
        if args.save_dir:
            os.makedirs(args.save_dir, exist_ok=True)
            cv2.imwrite(os.path.join(args.save_dir, os.path.basename(p)), draw(img, r))


if __name__ == '__main__':
    main()
