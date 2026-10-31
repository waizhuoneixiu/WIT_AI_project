# -*- coding: utf-8 -*-
"""在 NEU-DET 六类上微调（可选先用 Severstal 跨厂权重初始化，并启用强增强）。

用法：
  python scripts/finetune_neu.py --init runs/severstal_bin/weights/best.pt --name n640_ft_sev_aug
  python scripts/finetune_neu.py --init yolo26n.pt --name n640_aug --epochs 120
"""
import argparse
import os

from ultralytics import YOLO

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
DATA = os.path.join(PROJ, 'data', 'neu_det', 'data.yaml')
RUNS = os.path.join(PROJ, 'runs')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', required=True, help='初始权重（跨厂预训练 best.pt 或 yolo26n.pt）')
    ap.add_argument('--name', required=True)
    ap.add_argument('--data', default=os.path.join(PROJ, 'data', 'neu_det', 'data.yaml'))
    ap.add_argument('--epochs', type=int, default=120)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--imgsz', type=int, default=640)
    ap.add_argument('--lr0', type=float, default=0.005)
    ap.add_argument('--strong-aug', action='store_true', default=False)
    args = ap.parse_args()

    init = args.init
    if not os.path.isabs(init):
        cand = os.path.join(PROJ, init)
        init = cand if os.path.exists(cand) else init
    print('init weights:', init, '| exists:', os.path.exists(init))
    print('data:', args.data)
    model = YOLO(init)
    kwargs = dict(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=0,
        workers=4,
        patience=40,
        seed=0,
        amp=True,
        cos_lr=True,
        close_mosaic=10,
        optimizer='auto',
        lr0=args.lr0,
        warmup_epochs=3.0,
        project=RUNS,
        name=args.name,
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    if args.strong_aug:
        # 模拟不同工厂/光照/拍摄条件，提升域泛化
        kwargs.update(dict(
            hsv_h=0.02, hsv_s=0.8, hsv_v=0.6,
            degrees=10.0, translate=0.15, scale=0.6, shear=2.0, perspective=0.0005,
            flipud=0.2, fliplr=0.5,
            mosaic=1.0, mixup=0.15, erasing=0.45,
            auto_augment='randaugment',
            multi_scale=0.2,
        ))
    model.train(**kwargs)
    print('BEST:', os.path.join(RUNS, args.name, 'weights', 'best.pt'))


if __name__ == '__main__':
    main()
