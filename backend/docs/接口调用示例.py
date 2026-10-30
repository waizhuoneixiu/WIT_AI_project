# -*- coding: utf-8 -*-
"""SteelScan 后端 API 调用示例（Windows / Python 3.12）。

用法：
    1) 先启动服务：python server.py --port 8000
    2) 运行本示例：python docs/接口调用示例.py
可选：
    python docs/接口调用示例.py --base http://127.0.0.1:8000 --image data/neu_det/images/test/patches_110.jpg
"""
import argparse
import base64
import json
import os
import sys

import requests

DEFAULT_BASE = 'http://127.0.0.1:8000'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SteelScanClient:
    """SteelScan 缺陷检测后端客户端。"""

    def __init__(self, base_url=DEFAULT_BASE, timeout=60):
        self.base = base_url.rstrip('/')
        self.timeout = timeout

    def health(self):
        return requests.get(self.base + '/health', timeout=self.timeout).json()

    def model_info(self):
        return requests.get(self.base + '/model/info', timeout=self.timeout).json()

    def classes(self):
        return requests.get(self.base + '/classes', timeout=self.timeout).json()

    def detect(self, image_path):
        """单图检测。"""
        with open(image_path, 'rb') as f:
            files = {'image': (os.path.basename(image_path), f, 'image/jpeg')}
            r = requests.post(self.base + '/detect', files=files, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def detect_batch(self, image_paths):
        """批量检测（可多文件）。"""
        files = []
        for p in image_paths:
            files.append(('images', (os.path.basename(p), open(p, 'rb'), 'image/jpeg')))
        try:
            r = requests.post(self.base + '/detect/batch', files=files, timeout=self.timeout)
        finally:
            for _, (_, fh, _) in files:
                fh.close()
        r.raise_for_status()
        return r.json()

    def detect_base64(self, image_path, conf=None, imgsz=None):
        """Base64 检测，可覆盖 conf/imgsz。"""
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        payload = {'image_base64': b64, 'filename': os.path.basename(image_path)}
        if conf is not None:
            payload['conf'] = conf
        if imgsz is not None:
            payload['imgsz'] = imgsz
        r = requests.post(self.base + '/detect/base64', json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=DEFAULT_BASE)
    ap.add_argument('--image', default=os.path.join(ROOT, 'data', 'neu_det', 'images', 'test', 'patches_110.jpg'))
    args = ap.parse_args()

    c = SteelScanClient(args.base)
    print('== /health ==')
    print(json.dumps(c.health(), ensure_ascii=False))
    print('\n== /model/info ==')
    print(json.dumps(c.model_info(), ensure_ascii=False, indent=2))
    print('\n== /classes ==')
    print(json.dumps(c.classes(), ensure_ascii=False))

    if not os.path.exists(args.image):
        raise SystemExit('示例图片不存在: %s' % args.image)
    print('\n== POST /detect ==', args.image)
    r = c.detect(args.image)
    print(json.dumps(r, ensure_ascii=False, indent=2))

    print('\n== POST /detect/base64 (conf=0.10) ==')
    r2 = c.detect_base64(args.image, conf=0.10)
    print(json.dumps({'defect_count': r2['defect_count'], 'inference_ms': r2['inference_ms'],
                      'defects': [{'class': d['class_name'], 'conf': d['confidence']} for d in r2['defects']]},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
