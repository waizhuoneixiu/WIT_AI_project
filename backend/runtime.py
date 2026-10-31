# -*- coding: utf-8 -*-
"""模型运行时：权重选择 + 检测器单例（server.py 与 api_v1.py 共用）。"""
import glob
import os
import threading

import config
from cloud_detector import DetectionError, MODEL_VERSION, ModelScopeDetector

_lock = threading.Lock()
_detector = None
_weights_path = None


def pick_weights():
    """Only explicit local mode uses trained six-class weights."""
    candidates = []
    run_bests = sorted(glob.glob(os.path.join(config.RUNS_DIR, '*', 'weights', 'best.pt')),
                       key=os.path.getmtime, reverse=True)
    candidates += run_bests
    candidates += [config.BEST_WEIGHTS, os.path.join(config.MODELS_DIR, 'best.pt')]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('未找到可用模型权重（%s）' % config.BEST_WEIGHTS)


def get_detector():
    """Lazy singleton; cloud mode never imports a local model runtime."""
    global _detector, _weights_path
    if _detector is None:
        with _lock:
            if _detector is None:
                if config.DETECTOR_PROVIDER == 'modelscope':
                    _detector = ModelScopeDetector()
                elif config.DETECTOR_PROVIDER == 'local':
                    from detector import DefectDetector
                    _weights_path = pick_weights()
                    _detector = DefectDetector(weights=_weights_path, imgsz=config.DEFAULT_IMGSZ,
                                               conf=config.DEFAULT_CONF, iou=config.DEFAULT_IOU,
                                               device=config.DEFAULT_DEVICE)
                    _detector.warmup()
                else:
                    raise DetectionError(503, '未知检测服务配置')
    return _detector


def weights_path():
    if _weights_path is None:
        get_detector()
    return _weights_path


def model_info():
    """Configuration metadata, without loading weights or calling a cloud model."""
    import contract
    info = {'provider': config.DETECTOR_PROVIDER, 'imgsz': config.DEFAULT_IMGSZ,
            'conf_threshold': config.DEFAULT_CONF, 'iou_threshold': config.DEFAULT_IOU,
            'classes': {c['class_id']: c['class_name'] for c in contract.classes()}}
    if config.DETECTOR_PROVIDER == 'modelscope':
        return {**info, 'model_version': MODEL_VERSION, 'weights_file': 'best.onnx',
                'device': 'remote-cpu', 'configured': bool(config.MODELSCOPE_API_TOKEN)}
    if config.DETECTOR_PROVIDER == 'local':
        weights = pick_weights()
        return {**info, 'model_version': os.path.basename(weights), 'weights': weights,
                'weights_file': os.path.basename(weights), 'device': str(config.DEFAULT_DEVICE),
                'weights_size_mb': round(os.path.getsize(weights) / 1e6, 2), 'configured': True}
    raise DetectionError(503, '未知检测服务配置')
