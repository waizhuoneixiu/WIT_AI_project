# -*- coding: utf-8 -*-
"""SteelScan 缺陷检测后端服务（FastAPI）。

启动：
    python server.py                 # 默认 0.0.0.0:8000
    python server.py --port 8010
    uvicorn server:app --host 0.0.0.0 --port 8000

接口分两层：
1) 低层检测接口（demo/快速联调）：
   GET  /health, /model/info, /classes
   POST /detect, /detect/batch, /detect/base64
2) 团队共同接口（按 docs/plans/04-shared-contract.md）：
   POST /api/inspections, GET /api/inspections, GET /api/inspections/{id}
   GET  /api/tasks/{task_id}, POST /api/inspections/{id}/analysis
   POST /api/chat/messages, POST /api/inspections/{id}/review
   GET  /api/batches/{batch_no}/summary, GET /api/reports/{id}
   WS   /ws/tasks/{task_id}, GET /api/class-map
3) 静态文件：/files/...（检测标注图）
"""
import argparse
import base64
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

config.load_dotenv_if_present()

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import api_v1  # noqa: E402
import contract  # noqa: E402
import runtime  # noqa: E402
import storage  # noqa: E402
from security import verify_api_key  # noqa: E402

APP_VERSION = '1.2.0'


def _decode_image(data):
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail='无法解码图片（请上传 jpg/png/bmp）')
    return img


class Base64Request(BaseModel):
    image_base64: str
    filename: str = 'base64_image.jpg'
    conf: float = None
    imgsz: int = None


storage.init_db()

app = FastAPI(title='SteelScan 缺陷检测 API', version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(api_v1.router)
app.include_router(api_v1.ws_router)
os.makedirs(storage.IMAGES_DIR, exist_ok=True)
app.mount('/files', StaticFiles(directory=storage.IMAGES_DIR), name='files')


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'service': 'steelscan-defect-api',
        'api_version': APP_VERSION,
        'version': APP_VERSION,
        'model_loaded': runtime._detector is not None,
        'auth_required': bool(config.API_KEY),
        'storage': storage.DB_PATH,
        'contract_classes': contract.classes(),
    }


@app.get('/classes')
def classes():
    return {'classes': [{'id': c['class_id'], 'name': c['class_name'], 'name_cn': c['class_cn']}
                        for c in contract.classes()]}


@app.get('/model/info')
def model_info(_: None = Depends(verify_api_key)):
    d = runtime.get_detector()
    return {
        'weights': d.weights,
        'weights_file': os.path.basename(d.weights),
        'imgsz': d.imgsz,
        'conf_threshold': d.conf,
        'iou_threshold': d.iou,
        'device': str(d.device),
        'classes': {c['class_id']: c['class_name'] for c in contract.classes()},
        'weights_size_mb': round(os.path.getsize(d.weights) / 1e6, 2),
    }


@app.post('/detect')
async def detect(image: UploadFile = File(...), _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    data = await image.read()
    img = _decode_image(data)
    result = runtime.get_detector().detect(img)
    result['filename'] = image.filename
    result['elapsed_ms'] = round((time.perf_counter() - t0) * 1000.0, 2)
    return result


@app.post('/detect/batch')
async def detect_batch(images: list[UploadFile] = File(...), _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    results = []
    for f in images:
        data = await f.read()
        img = _decode_image(data)
        r = runtime.get_detector().detect(img)
        r['filename'] = f.filename
        results.append(r)
    return {'count': len(results), 'elapsed_ms': round((time.perf_counter() - t0) * 1000.0, 2),
            'results': results}


@app.post('/detect/base64')
def detect_base64(req: Base64Request, _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    try:
        raw = base64.b64decode(req.image_base64.split(',')[-1])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail='base64 解码失败: %s' % e)
    img = _decode_image(raw)
    result = runtime.get_detector().detect(img, conf=req.conf, imgsz=req.imgsz)
    result['filename'] = req.filename
    result['elapsed_ms'] = round((time.perf_counter() - t0) * 1000.0, 2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--reload', action='store_true')
    args = ap.parse_args()
    print('weights:', runtime.pick_weights())
    print('storage:', storage.DB_PATH)
    print('启动 API: http://%s:%d/docs' % ('127.0.0.1' if args.host == '0.0.0.0' else args.host, args.port))
    import uvicorn
    uvicorn.run('server:app', host=args.host, port=args.port, reload=args.reload)


if __name__ == '__main__':
    main()
