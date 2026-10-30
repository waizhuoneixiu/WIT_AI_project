# -*- coding: utf-8 -*-
"""模型卡生成：读取评测 JSON 生成 Markdown 模型卡（用于比赛文档）。"""
import argparse
import glob
import json
import os

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(DEV, 'runs')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True, help='实验名，如 n320')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    eval_path = os.path.join(RUNS, 'eval_%s.json' % args.name)
    bench_path = os.path.join(RUNS, 'benchmark_%s_*.json' % args.name)
    if not os.path.exists(eval_path):
        raise SystemExit('评测文件不存在: %s' % eval_path)
    with open(eval_path, encoding='utf-8') as f:
        ev = json.load(f)
    bench = None
    for p in glob.glob(bench_path):
        with open(p, encoding='utf-8') as f:
            bench = json.load(f)
        break

    lines = []
    lines.append('# 模型卡：SteelScan 带钢表面缺陷检测模型（%s）' % args.name)
    lines.append('')
    lines.append('> 自动生成，数据来源 NEU-DET（东北大学表面缺陷数据库）')
    lines.append('')
    lines.append('## 概要')
    lines.append('')
    lines.append('| 项目 | 内容 |')
    lines.append('| --- | --- |')
    lines.append('| 任务 | 6 类热轧带钢表面缺陷目标检测 |')
    lines.append('| 基础模型 | YOLO26n（ultralytics 8.4.193，COCO 预训练迁移） |')
    lines.append('| 参数量 | 2.4M（约 2.39M） |')
    lines.append('| 计算量 | 5.4 GFLOPs |')
    lines.append('| 输入尺寸 | %d×%d |' % (ev.get('imgsz', 320), ev.get('imgsz', 320)))
    lines.append('| 测试集 | %d 张（NEU-DET test split） |' % ev.get('test_images', 0))
    lines.append('')
    lines.append('## 测试集指标（IoU=0.5）')
    lines.append('')
    lines.append('| 指标 | 数值 |')
    lines.append('| --- | --- |')
    for k, label in [('mAP50', 'mAP50'), ('mAP50-95', 'mAP50-95'), ('precision', 'Precision'),
                     ('recall', 'Recall'), ('image_hit_rate', '图片级检出率'), ('miss_rate', '图片级漏检率'),
                     ('avg_boxes_per_image', '平均预测框数/图')]:
        if k in ev:
            lines.append('| %s | %s |' % (label, ev[k]))
    if 'avg_inference_ms' in ev:
        lines.append('| 平均推理时延(GPU) | %s ms |' % ev['avg_inference_ms'])
    if 'fps_est' in ev:
        lines.append('| 估计 FPS | %s |' % ev['fps_est'])
    lines.append('')
    lines.append('## 逐类指标')
    lines.append('')
    lines.append('| 缺陷类别 | AP50 | AP50-95 | Precision | Recall |')
    lines.append('| --- | --- | --- | --- | --- |')
    cn = {'rolled-in_scale': '氧化铁皮压入', 'patches': '斑块', 'crazing': '龟裂',
          'pitted_surface': '麻点', 'inclusion': '夹杂', 'scratches': '划伤'}
    for name, m in (ev.get('per_class') or {}).items():
        lines.append('| %s / %s | %s | %s | %s | %s |' % (
            cn.get(name, name), name, m.get('AP50'), m.get('AP50-95'), m.get('precision'), m.get('recall')))
    lines.append('')
    if bench:
        lines.append('## 推理时延基准')
        lines.append('')
        for key in ('gpu', 'cpu'):
            b = bench.get(key)
            if b:
                lines.append('- %s：mean %s ms / p95 %s ms / %s FPS（%d 张测试图）' % (
                    key.upper(), b.get('mean_ms'), b.get('p95_ms'), b.get('fps'), b.get('images')))
        lines.append('')
    lines.append('## 局限与说明')
    lines.append('')
    lines.append('- 数据为公开学术数据集 NEU-DET，200×200 灰度图；真实产线需补充现场数据做领域适配。')
    lines.append('- 指标为离线测试集结果，实际部署需按产线节拍与漏检/过杀要求调整业务阈值。')
    lines.append('- 引用：K. Song, Y. Yan, Applied Surface Science 285 (2013) 858-864；Y. He et al., IEEE TIM 69(4) (2020) 1493-1504。')
    lines.append('- 框架：ultralytics（AGPL-3.0）；比赛演示用途，商业化部署需评估授权。')
    lines.append('')

    out = args.out or os.path.join(DEV, 'docs', '模型卡_%s.md' % args.name)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('模型卡已生成:', out)


if __name__ == '__main__':
    main()
