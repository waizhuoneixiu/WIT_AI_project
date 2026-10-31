# -*- coding: utf-8 -*-
"""阶段 1：在 Severstal（另一家钢厂）二分类缺陷数据上预训练 YOLO26n。"""
import os

from ultralytics import YOLO

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
DATA = os.path.join(PROJ, 'data', 'severstal_yolo', 'data.yaml')
PRE = os.path.join(PROJ, 'yolo26n.pt')


def main():
    print('pretrained weights:', PRE, os.path.exists(PRE))
    model = YOLO(PRE)
    model.train(
        data=DATA,
        epochs=20,
        imgsz=640,
        batch=16,
        device=0,
        workers=4,
        seed=0,
        project=os.path.join(PROJ, 'runs'),
        name='severstal_bin',
        exist_ok=True,
        patience=8,
        plots=True,
        verbose=True,
    )


if __name__ == '__main__':
    main()
