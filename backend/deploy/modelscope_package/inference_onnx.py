# -*- coding: utf-8 -*-
"""ONNX Runtime 推理（用于魔搭/无 GPU 环境，不需要安装 PyTorch）。

输入：BGR ndarray 或图片路径
输出：与后端 /detect 一致的结构化 dict
"""
import os
import time

import cv2
import numpy as np

import contract

# 模型原始训练类别顺序（勿改，与 best.onnx 输出一致）
CLASSES = contract.RAW_CLASSES


def letterbox(im, new_shape=(640, 640), color=(114, 114, 114)):
    shape = im.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw = (new_shape[1] - new_unpad[0]) / 2.0
    dh = (new_shape[0] - new_unpad[1]) / 2.0
    if shape[::-1] != new_unpad:
        im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im = cv2.copyMakeBorder(im, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return im, r, (left, top)


def nms(boxes, scores, iou_thres=0.45):
    """纯 numpy NMS，返回保留索引。"""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        inds = np.where(iou <= iou_thres)[0]
        order = order[inds + 1]
    return keep


class OnnxDetector:
    """YOLO26n ONNX 检测器（CPU 推理）。"""

    def __init__(self, model_path, imgsz=640, conf=0.25, iou=0.45):
        import onnxruntime as ort
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.model_path = model_path
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.warmup()

    def warmup(self):
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        try:
            self.detect(dummy)
        except Exception:
            pass

    def detect(self, image, conf=None, iou=None):
        conf = self.conf if conf is None else conf
        iou = self.iou if iou is None else iou
        t0 = time.perf_counter()
        if isinstance(image, str):
            # 用 fromfile+imdecode，兼容 Windows 中文/含空格路径
            data = np.fromfile(image, dtype=np.uint8)
            im = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if im is None:
                raise ValueError('无法读取图片: %s' % image)
        else:
            im = image
        h0, w0 = im.shape[:2]
        im_lb, r, pad = letterbox(im, (self.imgsz, self.imgsz))
        blob = np.ascontiguousarray(im_lb[:, :, ::-1].transpose(2, 0, 1)[None]).astype(np.float32) / 255.0
        out = self.session.run(None, {self.input_name: blob})[0]  # (1, 4+nc, N)
        pred = out[0].T  # (N, 4+nc)
        boxes_xywh = pred[:, :4]
        scores = pred[:, 4:]
        cls_ids = scores.argmax(axis=1)
        confs = scores[np.arange(len(scores)), cls_ids]
        mask = confs >= conf
        boxes_xywh, cls_ids, confs = boxes_xywh[mask], cls_ids[mask], confs[mask]

        if len(boxes_xywh) > 0:
            cx, cy, bw, bh = boxes_xywh[:, 0], boxes_xywh[:, 1], boxes_xywh[:, 2], boxes_xywh[:, 3]
            boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
            keep = nms(boxes, confs, iou)
            boxes = boxes[keep].astype(np.float32)
            cls_ids = cls_ids[keep]
            confs = confs[keep]
            # 还原到原图坐标
            boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad[0]) / r
            boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad[1]) / r
            boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w0)
            boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h0)
        else:
            boxes = np.zeros((0, 4), np.float32)
            cls_ids = np.zeros((0,), np.int64)
            confs = np.zeros((0,), np.float32)

        defects = []
        for box, cid, c in zip(boxes, cls_ids, confs):
            cid = int(cid)
            raw_name = CLASSES[cid]
            cc = contract.contract_class(raw_name)
            x1, y1, x2, y2 = [float(v) for v in box]
            defects.append({
                'class_id': cc['class_id'],
                'class_name': cc['class_name'],
                'class_cn': cc['class_cn'],
                'raw_class_name': raw_name,
                'confidence': round(float(c), 4),
                'bbox_xyxy': [round(v, 2) for v in (x1, y1, x2, y2)],
                'area_ratio': round(max(0.0, min(1.0, (x2 - x1) * (y2 - y1) / float(w0 * h0))), 4),
                'width': round(x2 - x1, 2),
                'height': round(y2 - y1, 2),
            })
        defects.sort(key=lambda d: d['confidence'], reverse=True)
        elapsed = (time.perf_counter() - t0) * 1000.0
        return {
            'image': os.path.basename(image) if isinstance(image, str) else '<array>',
            'width': int(w0),
            'height': int(h0),
            'defect_count': len(defects),
            'defects': defects,
            'inference_ms': round(elapsed, 2),
            'model': os.path.basename(self.model_path),
            'imgsz': self.imgsz,
        }
