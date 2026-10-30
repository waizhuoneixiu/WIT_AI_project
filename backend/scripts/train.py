# -*- coding: utf-8 -*-
"""YOLO26 训练入口（支持实验矩阵参数）。"""
import argparse
import os
import sys

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(DEV, '.ultralytics'))
os.environ.setdefault('MPLCONFIGDIR', os.path.join(DEV, '.mpl'))
sys.path.insert(0, DEV)

from ultralytics import YOLO  # noqa: E402

from config import DATA_YAML, MODELS_DIR, RUNS_DIR  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='yolo26n.pt', help='预训练权重名或绝对路径')
    ap.add_argument('--name', default='n320')
    ap.add_argument('--imgsz', type=int, default=320)
    ap.add_argument('--epochs', type=int, default=200)
    ap.add_argument('--batch', type=int, default=16)
    ap.add_argument('--device', default='0')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--patience', type=int, default=40)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--cls-pw', type=float, default=0.0)
    ap.add_argument('--freeze', type=int, default=0)
    ap.add_argument('--lr0', type=float, default=0.01)
    ap.add_argument('--optimizer', default='auto')
    ap.add_argument('--no-amp', action='store_true')
    ap.add_argument('--cache', action='store_true')
    args = ap.parse_args()

    weights = args.model
    if not os.path.isabs(weights):
        cand = os.path.join(MODELS_DIR, weights)
        weights = cand if os.path.exists(cand) else weights
    print('weights:', weights)
    print('data:', DATA_YAML)

    model = YOLO(weights)
    train_kwargs = dict(
        data=DATA_YAML,
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        seed=args.seed,
        amp=not args.no_amp,
        cos_lr=True,
        close_mosaic=10,
        optimizer=args.optimizer,
        lr0=args.lr0,
        project=RUNS_DIR,
        name=args.name,
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    if args.cls_pw > 0:
        train_kwargs['cls_pw'] = args.cls_pw
    if args.freeze:
        train_kwargs['freeze'] = args.freeze
    if args.cache:
        train_kwargs['cache'] = True

    model.train(**train_kwargs)
    best = os.path.join(RUNS_DIR, args.name, 'weights', 'best.pt')
    print('BEST_WEIGHTS:', best, 'exists:', os.path.exists(best))


if __name__ == '__main__':
    main()
