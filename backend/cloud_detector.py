"""ModelScope Gradio transport; inference runs only in the configured cloud studio."""
import json
import math
import re
import time
from urllib.parse import urlsplit

import cv2
import requests
from urllib3.exceptions import ReadTimeoutError

import config
import contract

MODEL_VERSION = 'yolo26n-640-onnx'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class DetectionError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_result(result, width, height):
    """Reject corrupt upstream output instead of treating it as a successful empty result."""
    try:
        if not isinstance(result, dict):
            raise ValueError()
        if type(result['width']) is not int or type(result['height']) is not int:
            raise ValueError()
        if (result['width'], result['height']) != (width, height) or result['imgsz'] != 640:
            raise ValueError()
        defects = result['defects']
        if not isinstance(defects, list) or type(result['defect_count']) is not int:
            raise ValueError()
        if result['defect_count'] != len(defects) or len(defects) > 1000:
            raise ValueError()
        if not _finite(result['inference_ms']) or result['inference_ms'] < 0:
            raise ValueError()
        normalized = []
        for defect in defects:
            if type(defect['class_id']) is not int:
                raise ValueError()
            cls = contract.class_by_id(defect['class_id'])
            if cls['class_name'] != defect['class_name']:
                raise ValueError()
            score = defect['confidence']
            box = defect['bbox_xyxy']
            if not _finite(score) or not 0 <= score <= 1:
                raise ValueError()
            if not isinstance(box, list) or len(box) != 4 or not all(map(_finite, box)):
                raise ValueError()
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError()
            normalized.append({**cls, 'confidence': score, 'bbox_xyxy': box,
                               'area_ratio': (x2-x1)*(y2-y1)/(width*height),
                               'width': x2-x1, 'height': y2-y1})
        return {'image': '<array>', 'width': width, 'height': height,
                'defect_count': len(normalized), 'defects': normalized,
                'inference_ms': result['inference_ms'], 'model': MODEL_VERSION, 'imgsz': 640}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DetectionError(502, '云检测返回无效结果，请稍后重试') from None


class ModelScopeDetector:
    def __init__(self):
        self.base_url = config.MODELSCOPE_BASE_URL
        self.token = config.MODELSCOPE_API_TOKEN
        self.timeout = config.MODELSCOPE_TIMEOUT

    def _check_config(self):
        try:
            url = urlsplit(self.base_url)
            valid_url = (url.scheme == 'https' and url.hostname
                         and url.hostname.endswith('.api-inference.modelscope.net')
                         and not url.username and not url.password and url.path in ('', '/')
                         and not url.query and not url.fragment and url.port in (None, 443))
        except ValueError:
            valid_url = False
        if not valid_url:
            raise DetectionError(503, '魔搭 API 地址配置无效')
        if not self.token:
            raise DetectionError(503, '后端尚未配置魔搭访问令牌')
        if not _finite(self.timeout) or not 1 <= self.timeout <= 300:
            raise DetectionError(503, '魔搭超时配置无效')

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DetectionError(504, '云检测超时，请先查询历史确认结果')
        return remaining

    def _request(self, session, method, path, deadline, **kwargs):
        remaining = self._remaining(deadline)
        response = session.request(method, self.base_url + path,
                                   headers={'Authorization': 'Bearer ' + self.token},
                                   timeout=(min(10, remaining), remaining),
                                   allow_redirects=False, stream=True, **kwargs)
        if response.status_code in (401, 403):
            response.close()
            raise DetectionError(503, '魔搭服务鉴权失败，请检查后端配置')
        if response.status_code != 200:
            response.close()
            raise DetectionError(502, '云检测服务暂时不可用，请稍后重试')
        return response

    def _json(self, response, deadline):
        with response:
            data = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                self._remaining(deadline)
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise DetectionError(502, '云检测响应超出限制')
            return json.loads(data)

    def _completion(self, response, deadline):
        with response:
            event, data, count, buffer = '', [], 0, bytearray()
            # Gradio can send tiny heartbeats; do not buffer them past the deadline.
            for chunk in response.iter_content(chunk_size=1):
                self._remaining(deadline)
                count += len(chunk)
                if count > MAX_RESPONSE_BYTES:
                    raise DetectionError(502, '云检测响应超出限制')
                for byte in chunk:
                    if byte != 10:
                        buffer.append(byte)
                        continue
                    line = buffer.rstrip(b'\r').decode('utf-8')
                    buffer.clear()
                    if not line:
                        if event == 'error':
                            raise DetectionError(502, '云检测执行失败，请稍后重试')
                        if event == 'complete':
                            values = json.loads('\n'.join(data))
                            if not isinstance(values, list) or len(values) != 4:
                                raise ValueError()
                            result = values[1]
                            return json.loads(result) if isinstance(result, str) else result
                        event, data = '', []
                    elif line.startswith('event:'):
                        event = line[6:].strip()
                    elif line.startswith('data:'):
                        data.append(line[5:].lstrip())
        raise DetectionError(502, '云检测未返回完成结果，请稍后重试')

    def detect(self, image, conf=None, iou=None, imgsz=None):
        self._check_config()
        conf = config.DEFAULT_CONF if conf is None else conf
        if not _finite(conf) or not 0 <= conf <= 1:
            raise DetectionError(422, '检测阈值必须在 0 到 1 之间')
        if imgsz not in (None, 640) or iou not in (None, .45):
            raise DetectionError(422, '当前云模型仅支持 imgsz=640、iou=0.45')
        height, width = image.shape[:2]
        encoded, png = cv2.imencode('.png', image)
        if not encoded:
            raise DetectionError(400, '无法编码待检测图片')
        deadline = time.monotonic() + self.timeout
        try:
            # A request owns its session; concurrent uploads never share mutable session state.
            with requests.Session() as session:
                uploaded = self._json(self._request(
                    session, 'POST', '/gradio_api/upload', deadline,
                    files={'files': ('inspection.png', png.tobytes(), 'image/png')}), deadline)
                if (not isinstance(uploaded, list) or len(uploaded) != 1
                        or not isinstance(uploaded[0], str) or not uploaded[0]):
                    raise ValueError()
                call = self._json(self._request(
                    session, 'POST', '/gradio_api/call/detect_ui', deadline,
                    json={'data': [{'path': uploaded[0], 'meta': {'_type': 'gradio.FileData'}}, conf]}),
                    deadline)
                event_id = call['event_id']
                if not isinstance(event_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', event_id):
                    raise ValueError()
                result = self._completion(self._request(
                    session, 'GET', '/gradio_api/call/detect_ui/' + event_id, deadline), deadline)
                return validate_result(result, width, height)
        except requests.Timeout:
            raise DetectionError(504, '云检测超时，请先查询历史确认结果') from None
        except requests.ConnectionError as error:
            if error.args and isinstance(error.args[0], ReadTimeoutError):
                raise DetectionError(504, '云检测超时，请先查询历史确认结果') from None
            raise DetectionError(502, '无法连接云检测服务，请检查网络') from None
        except requests.RequestException:
            raise DetectionError(502, '无法连接云检测服务，请检查网络') from None
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise DetectionError(502, '云检测返回无效响应，请稍后重试') from None
