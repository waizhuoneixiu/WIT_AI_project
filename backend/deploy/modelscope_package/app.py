# -*- coding: utf-8 -*-
"""SteelScan 智检 Agent — 魔搭创空间 Gradio 演示页（ONNX CPU 推理，无需 PyTorch）。

启动（本地）：
    python app.py
部署：上传本目录到魔搭创空间（Gradio SDK），平台会自动运行 app.py。
"""
import json
import os
import sys

import gradio as gr
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from inference_onnx import OnnxDetector  # noqa: E402

MODEL_PATH = os.path.join(ROOT, 'models', 'best.onnx')
DETECTOR = OnnxDetector(MODEL_PATH, imgsz=640, conf=0.25, iou=0.45)

COLORS = {
    'rolled-in_scale': (255, 140, 0),
    'patches': (220, 20, 60),
    'crazing': (30, 144, 255),
    'pitted_surface': (148, 0, 211),
    'inclusion': (0, 170, 120),
    'scratches': (255, 215, 0),
}

APP_TITLE = 'SteelScan 智检 Agent — 带钢表面缺陷检测'
APP_DESC = 'YOLO26n 小模型（2.4M 参数 / 5.4 GFLOPs）实时检测热轧带钢 6 类表面缺陷；CPU 推理，单张约 20~60ms。上传图片或使用下方样例图体验。'


def _draw(image_rgb: Image.Image, result: dict) -> Image.Image:
    out = image_rgb.copy()
    draw = ImageDraw.Draw(out)
    for d in result.get('defects', []):
        x1, y1, x2, y2 = d['bbox_xyxy']
        color = COLORS.get(d['class_name'], (255, 0, 0))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = '%s %.2f' % (d['class_name'], d['confidence'])
        try:
            tb = draw.textbbox((x1, max(0, y1 - 12)), label)
            draw.rectangle(tb, fill=color)
        except Exception:
            pass
        draw.text((x1, max(0, y1 - 12)), label, fill=(0, 0, 0))
    return out


def detect_ui(image, conf):
    """Gradio 检测回调。返回：标注图、JSON、表格、摘要。"""
    if image is None:
        return None, '{}', [], '请先上传一张图片'
    conf = float(conf)
    rgb = np.array(image.convert('RGB'))
    bgr = rgb[:, :, ::-1].copy()
    result = DETECTOR.detect(bgr, conf=conf)
    annotated = _draw(image.convert('RGB'), result)
    table = [[d['class_name'], d['class_cn'], round(d['confidence'], 4),
              str(d['bbox_xyxy']), d['area_ratio']] for d in result['defects']]
    if result['defect_count'] == 0:
        summary = '未检出缺陷（OK）'
    else:
        names = {}
        for d in result['defects']:
            names[d['class_cn']] = names.get(d['class_cn'], 0) + 1
        summary = '检出 %d 处缺陷：' % result['defect_count'] + '、'.join('%s×%d' % (k, v) for k, v in names.items())
        summary += '；最高置信度 %.3f；推理 %.1f ms' % (result['defects'][0]['confidence'], result['inference_ms'])
    return annotated, json.dumps(result, ensure_ascii=False, indent=2), table, summary


EXAMPLES = []
_samples_dir = os.path.join(ROOT, 'samples')
if os.path.isdir(_samples_dir):
    for _name in sorted(os.listdir(_samples_dir)):
        if _name.lower().endswith(('.jpg', '.jpeg', '.png')):
            EXAMPLES.append([os.path.join(_samples_dir, _name), 0.25])

with gr.Blocks(title=APP_TITLE) as demo:
    gr.Markdown('# ' + APP_TITLE)
    gr.Markdown(APP_DESC)
    with gr.Row():
        with gr.Column(scale=1):
            image_in = gr.Image(label='上传待检图片', type='pil')
            conf_slider = gr.Slider(0.05, 0.9, value=0.25, step=0.05, label='置信度阈值 conf（越低越灵敏，漏检少但误报多）')
            btn = gr.Button('开始检测', variant='primary')
            if EXAMPLES:
                gr.Examples(examples=EXAMPLES[:6], inputs=[image_in], label='样例图（点击使用）')
        with gr.Column(scale=1):
            image_out = gr.Image(label='检测结果', type='pil')
            summary = gr.Markdown()
    with gr.Row():
        json_out = gr.JSON(label='结构化结果 JSON')
        table_out = gr.Dataframe(headers=['类别', '中文名', '置信度', 'bbox(xyxy)', '面积占比'],
                                 label='缺陷明细', interactive=False)
    btn.click(detect_ui, inputs=[image_in, conf_slider], outputs=[image_out, json_out, table_out, summary])
    gr.Markdown('---\n模型：YOLO26n@640（ultralytics 8.4.193，NEU-DET 训练）；'
                '测试集 mAP50=0.806 / Recall=0.766 / 图片级漏检率 2.59%。'
                '类别：氧化铁皮压入、斑块、龟裂、麻点、夹杂、划伤。')

if __name__ == '__main__':
    demo.launch(server_name='0.0.0.0', server_port=7860)
