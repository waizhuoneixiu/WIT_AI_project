# -*- coding: utf-8 -*-
"""模型运行时：权重选择 + 检测器单例（server.py 与 api_v1.py 共用）。"""
import glob
import os
import threading

import config
from detector import DefectDetector

_lock = threading.Lock()
_detector = None
_weights_path = None


def pick_weights():
    """权重选择优先级：runs 下最新 best.pt -> config.BEST_WEIGHTS -> COCO 预训练。"""
    candidates = []
    run_bests = sorted(glob.glob(os.path.join(config.RUNS_DIR, '*', 'weights', 'best.pt')),
                       key=os.path.getmtime, reverse=True)
    candidates += run_bests
    candidates += [config.BEST_WEIGHTS, config.PRETRAINED]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('未找到可用模型权重（%s）' % config.BEST_WEIGHTS)


def get_detector():
    """懒加载检测器（线程安全；首次约 2~4 秒）。"""
    global _detector, _weights_path
    if _detector is None:
        with _lock:
            if _detector is None:
                _weights_path = pick_weights()
                _detector = DefectDetector(weights=_weights_path, imgsz=config.DEFAULT_IMGSZ,
                                           conf=config.DEFAULT_CONF, iou=config.DEFAULT_IOU,
                                           device=config.DEFAULT_DEVICE)
                _detector.warmup()
    return _detector


def weights_path():
    if _weights_path is None:
        get_detector()
    return _weights_path
