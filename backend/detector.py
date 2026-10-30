# -*- coding: utf-8 -*-
"""YOLO 缺陷检测器封装（后端推理核心）。"""
import glob
import os
import time

import numpy as np

import contract
from config import (BEST_WEIGHTS, CLASSES, CLASSES_CN, DEFAULT_CONF, DEFAULT_DEVICE,
                    DEFAULT_IMGSZ, DEFAULT_IOU, PRETRAINED, RUNS_DIR)


def resolve_weights(weights=None):
    """权重选择优先级：显式指定 -> runs/*/weights/best.pt（最新）-> BEST_WEIGHTS -> 预训练。"""
    if weights:
        return weights
    cand = sorted(glob.glob(os.path.join(RUNS_DIR, '*', 'weights', 'best.pt')),
                  key=os.path.getmtime, reverse=True)
    for p in cand + [BEST_WEIGHTS, PRETRAINED]:
        if p and os.path.exists(p):
            return p
    return PRETRAINED



class DefectDetector:
    """封装 ultralytics YOLO26，输出结构化检测结果。"""

    def __init__(self, weights=None, imgsz=None, conf=None, iou=None, device=None):
        from ultralytics import YOLO
        self.weights = resolve_weights(weights)
        if not os.path.exists(self.weights):
            raise FileNotFoundError('模型权重不存在: %s' % self.weights)
        self.model = YOLO(self.weights)
        self.imgsz = imgsz or DEFAULT_IMGSZ
        self.conf = DEFAULT_CONF if conf is None else conf
        self.iou = DEFAULT_IOU if iou is None else iou
        self.device = DEFAULT_DEVICE if device is None else device
        self.names = {i: n for i, n in enumerate(CLASSES)}
        self._warmed_up = False

    def warmup(self):
        """预热一次推理，避免首个请求包含 CUDA/加载初始化耗时。"""
        if self._warmed_up:
            return
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        try:
            self.model.predict(source=dummy, imgsz=self.imgsz, device=self._resolve_device(), verbose=False)
        except Exception:
            pass
        self._warmed_up = True

    def _resolve_device(self):
        if self.device == 'auto':
            try:
                import torch
                return 0 if torch.cuda.is_available() else 'cpu'
            except Exception:
                return 'cpu'
        return self.device

    def detect(self, image, conf=None, iou=None, imgsz=None):
        """检测单张图像。

        Args:
            image: 图片路径 或 numpy.ndarray 或 PIL.Image
        Returns:
            dict: 结构化结果（JSON 可序列化）
        """
        conf = self.conf if conf is None else conf
        iou = self.iou if iou is None else iou
        imgsz = self.imgsz if imgsz is None else imgsz
        t0 = time.perf_counter()
        results = self.model.predict(
            source=image, conf=conf, iou=iou, imgsz=imgsz,
            device=self._resolve_device(), verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        r = results[0]
        h, w = r.orig_shape[:2]
        defects = []
        boxes = r.boxes
        if boxes is not None and len(boxes) > 0:
            cls_ids = boxes.cls.tolist()
            confs = boxes.conf.tolist()
            xyxys = boxes.xyxy.tolist()
            for cid, c, xyxy in zip(cls_ids, confs, xyxys):
                cid = int(cid)
                raw_name = self.names.get(cid, str(cid))
                cc = contract.contract_class(raw_name)
                x1, y1, x2, y2 = [float(v) for v in xyxy]
                area_ratio = max(0.0, min(1.0, (x2 - x1) * (y2 - y1) / float(w * h)))
                defects.append({
                    'class_id': cc['class_id'],
                    'class_name': cc['class_name'],
                    'class_cn': cc['class_cn'],
                    'raw_class_id': cid,
                    'raw_class_name': raw_name,
                    'confidence': round(float(c), 4),
                    'bbox_xyxy': [round(v, 2) for v in (x1, y1, x2, y2)],
                    'area_ratio': round(area_ratio, 4),
                    'width': round(x2 - x1, 2),
                    'height': round(y2 - y1, 2),
                })
        defects.sort(key=lambda d: d['confidence'], reverse=True)
        return {
            'image': os.path.basename(image) if isinstance(image, str) else '<array>',
            'width': int(w),
            'height': int(h),
            'defect_count': len(defects),
            'defects': defects,
            'inference_ms': round(elapsed_ms, 2),
            'model': os.path.basename(self.weights),
            'imgsz': imgsz,
        }

    def detect_batch(self, images):
        """批量检测（逐张，便于展示单图耗时）。"""
        return [self.detect(img) for img in images]
