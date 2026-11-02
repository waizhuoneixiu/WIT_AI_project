# -*- coding: utf-8 -*-
"""GC10-DET 10 类辅助预训练：为 NEU 六类微调提供跨产线初始化。"""
import os

from ultralytics import YOLO

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
DATA = os.path.join(PROJ, 'data', 'gc10_yolo', 'data.yaml')
BASE = os.path.join(PROJ, 'weights', 'yolo26n.pt')
RUNS = os.path.join(PROJ, 'runs')


def main():
    print('data:', DATA, '| base:', BASE, '| exists:', os.path.exists(BASE), flush=True)
    model = YOLO(BASE)
    model.train(
        data=DATA,
        epochs=40,
        imgsz=640,
        batch=16,
        device=0,
        workers=4,
        patience=12,
        seed=0,
        amp=True,
        cos_lr=True,
        close_mosaic=8,
        optimizer='auto',
        lr0=0.01,
        warmup_epochs=3.0,
        project=RUNS,
        name='gc10_pretrain',
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    print('BEST:', os.path.join(RUNS, 'gc10_pretrain', 'weights', 'best.pt'), flush=True)


if __name__ == '__main__':
    main()
