# -*- coding: utf-8 -*-
"""模型导出（ONNX）+ 推理时延基准测试（GPU / CPU）。

用法：
    python scripts/benchmark.py --weights runs/n320/weights/best.pt --imgsz 320
"""
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

from config import DATA_DIR, RUNS_DIR  # noqa: E402


def collect_test_images(limit=None):
    test_dir = os.path.join(DATA_DIR, 'images', 'test')
    files = sorted(os.path.join(test_dir, f) for f in os.listdir(test_dir)
                   if f.lower().endswith(('.jpg', '.jpeg', '.bmp', '.png')))
    return files[:limit] if limit else files


def bench(model, files, imgsz, device, half=False, warmup=5):
    def run_one(p):
        return model.predict(source=p, imgsz=imgsz, device=device, verbose=False, half=half, conf=0.25)

    for p in files[:warmup]:
        run_one(p)
    lat = []
    for p in files:
        t0 = time.perf_counter()
        run_one(p)
        lat.append((time.perf_counter() - t0) * 1000.0)
    lat = np.array(lat)
    return {
        'device': str(device),
        'half': half,
        'imgsz': imgsz,
        'images': len(lat),
        'mean_ms': round(float(lat.mean()), 2),
        'p50_ms': round(float(np.percentile(lat, 50)), 2),
        'p95_ms': round(float(np.percentile(lat, 95)), 2),
        'fps': round(1000.0 / float(lat.mean()), 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', required=True)
    ap.add_argument('--imgsz', type=int, default=320)
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--export', action='store_true', help='同时导出 ONNX')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    files = collect_test_images(args.limit)
    print('bench images:', len(files))
    model = YOLO(args.weights)
    report = {'weights': args.weights}

    if args.export:
        try:
            onnx_path = model.export(format='onnx', imgsz=args.imgsz, opset=17, dynamic=False, simplify=False)
            report['onnx'] = onnx_path
            print('ONNX exported:', onnx_path)
        except Exception as e:
            report['onnx_error'] = repr(e)
            print('ONNX export failed:', e)

    try:
        report['gpu'] = bench(model, files, args.imgsz, device=0)
        print('GPU:', report['gpu'])
    except Exception as e:
        report['gpu_error'] = repr(e)
        print('GPU bench failed:', e)
    try:
        report['cpu'] = bench(model, files, args.imgsz, device='cpu')
        print('CPU:', report['cpu'])
    except Exception as e:
        report['cpu_error'] = repr(e)
        print('CPU bench failed:', e)

    out = args.out or os.path.join(RUNS_DIR, 'benchmark_%s_%d.json' % (os.path.basename(os.path.dirname(os.path.dirname(args.weights))), args.imgsz))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('saved:', out)


if __name__ == '__main__':
    main()
