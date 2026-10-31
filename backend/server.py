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
import binascii
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

import api_v1  # noqa: E402
import contract  # noqa: E402
import llm  # noqa: E402
import runtime  # noqa: E402
import storage  # noqa: E402
from security import verify_api_key  # noqa: E402
from cloud_detector import DetectionError  # noqa: E402

APP_VERSION = '1.3.0'


def _decode_image(data):
    if not data:
        raise HTTPException(status_code=400, detail='图片内容为空')
    if len(data) > api_v1.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail='图片超过 10MB 限制')
    arr = np.frombuffer(data, np.uint8)
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except cv2.error:
        img = None
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


@app.exception_handler(DetectionError)
async def detection_error_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={'detail': str(exc)})


@app.get('/files/{filename}', response_class=FileResponse)
def image_file(filename: str, _: None = Depends(verify_api_key)):
    image_root = os.path.realpath(storage.IMAGES_DIR)
    path = os.path.realpath(os.path.join(image_root, filename))
    if (os.path.dirname(path) != image_root or '\\' in filename or ':' in filename
            or not os.path.isfile(path)):
        raise HTTPException(status_code=404, detail='图片不存在')
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})


@app.get('/health')
def health():
    model = runtime.model_info()
    llm_info = llm.info()
    return {
        'status': 'ok',
        'service': 'steelscan-defect-api',
        'api_version': APP_VERSION,
        'version': APP_VERSION,
        'model_loaded': runtime._detector is not None,
        'auth_required': bool(config.API_KEY),
        'detector_provider': model['provider'],
        'detector_configured': model['configured'],
        'model_version': model['model_version'],
        'llm': {key: llm_info[key] for key in ('provider', 'mode', 'model', 'configured', 'source')},
        'contract_classes': contract.classes(),
    }


@app.get('/classes')
def classes():
    return {'classes': [{'id': c['class_id'], 'name': c['class_name'], 'name_cn': c['class_cn']}
                        for c in contract.classes()]}


@app.get('/model/info')
def model_info(_: None = Depends(verify_api_key)):
    return runtime.model_info()


def _detect_bytes(data, conf=None, imgsz=None):
    return runtime.get_detector().detect(_decode_image(data), conf=conf, imgsz=imgsz)


@app.post('/detect')
async def detect(image: UploadFile = File(...), _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    data = await image.read(api_v1.MAX_UPLOAD_BYTES + 1)
    result = await run_in_threadpool(_detect_bytes, data)
    result['filename'] = image.filename
    result['elapsed_ms'] = round((time.perf_counter() - t0) * 1000.0, 2)
    return result


@app.post('/detect/batch')
async def detect_batch(images: list[UploadFile] = File(...), _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    results = []
    for f in images:
        data = await f.read(api_v1.MAX_UPLOAD_BYTES + 1)
        r = await run_in_threadpool(_detect_bytes, data)
        r['filename'] = f.filename
        results.append(r)
    return {'count': len(results), 'elapsed_ms': round((time.perf_counter() - t0) * 1000.0, 2),
            'results': results}


@app.post('/detect/base64')
def detect_base64(req: Base64Request, _: None = Depends(verify_api_key)):
    t0 = time.perf_counter()
    try:
        if len(req.image_base64) > api_v1.MAX_UPLOAD_BYTES * 4 // 3 + 256:
            raise HTTPException(status_code=400, detail='图片超过 10MB 限制')
        raw = base64.b64decode(req.image_base64.split(',')[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail='base64 解码失败') from None
    result = _detect_bytes(raw, conf=req.conf, imgsz=req.imgsz)
    result['filename'] = req.filename
    result['elapsed_ms'] = round((time.perf_counter() - t0) * 1000.0, 2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--reload', action='store_true')
    args = ap.parse_args()
    print('detector:', runtime.model_info()['provider'])
    print('storage:', storage.DB_PATH)
    print('启动 API: http://%s:%d/docs' % ('127.0.0.1' if args.host == '0.0.0.0' else args.host, args.port))
    import uvicorn
    uvicorn.run('server:app', host=args.host, port=args.port, reload=args.reload)


if __name__ == '__main__':
    main()
