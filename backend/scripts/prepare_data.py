# -*- coding: utf-8 -*-
"""NEU-DET 数据准备：VOC XML -> YOLO 格式，并做分层划分。

用法：
    python scripts/prepare_data.py
输入：RAW_DIR（默认：deepseek-harness workspace 下的 NEU-DET 解压目录）
输出：data/neu_det/{images,labels}/{train,val,test} + data.yaml + data_meta.json
"""
import glob
import json
import os
import random
import shutil
import xml.etree.ElementTree as ET

# 本机路径（开发阶段）
WS = r'C:\Users\何ch\Documents\deepseek-harness\default-workspace'
DEV = os.path.join(WS, 'AIvision1_dev')
RAW_DIR = os.path.join(WS, 'neu_det_download', 'NEU-DET', 'NEU-DET')
OUT_DIR = os.path.join(DEV, 'data', 'neu_det')

# 固定类别顺序（与 XML 中 name 对应）
CLASSES = [
    'rolled-in_scale',
    'patches',
    'crazing',
    'pitted_surface',
    'inclusion',
    'scratches',
]
# 文件前缀 -> 类别（用于分层划分；xml 内 name 为准）
PREFIX_TO_CLASS = {
    'rolled-in_scale': 'rolled-in_scale',
    'rolled_in_scale': 'rolled-in_scale',
    'rs': 'rolled-in_scale',
    'patches': 'patches',
    'pa': 'patches',
    'crazing': 'crazing',
    'cr': 'crazing',
    'pitted_surface': 'pitted_surface',
    'ps': 'pitted_surface',
    'inclusion': 'inclusion',
    'in': 'inclusion',
    'scratches': 'scratches',
    'sc': 'scratches',
}
SPLIT_RATIO = (0.70, 0.15, 0.15)
SEED = 0


def parse_xml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    size = root.find('size')
    w = int(size.find('width').text)
    h = int(size.find('height').text)
    boxes = []
    for obj in root.findall('object'):
        name = obj.find('name').text.strip()
        b = obj.find('bndbox')
        xmin = float(b.find('xmin').text)
        ymin = float(b.find('ymin').text)
        xmax = float(b.find('xmax').text)
        ymax = float(b.find('ymax').text)
        boxes.append((name, xmin, ymin, xmax, ymax))
    return w, h, boxes, root.find('filename').text


def to_yolo_line(cls_id, w, h, xmin, ymin, xmax, ymax):
    # clamp & 归一化
    xmin = max(0.0, min(float(w), xmin))
    xmax = max(0.0, min(float(w), xmax))
    ymin = max(0.0, min(float(h), ymin))
    ymax = max(0.0, min(float(h), ymax))
    if xmax <= xmin or ymax <= ymin:
        return None
    cx = (xmin + xmax) / 2.0 / w
    cy = (ymin + ymax) / 2.0 / h
    bw = (xmax - xmin) / w
    bh = (ymax - ymin) / h
    return '%d %.6f %.6f %.6f %.6f' % (cls_id, cx, cy, bw, bh)


def main():
    xmls = sorted(glob.glob(os.path.join(RAW_DIR, 'ANNOTATIONS', '*.xml')))
    assert xmls, '未找到 XML: %s' % RAW_DIR
    print('XML 数量:', len(xmls))

    records = []
    name_counter = {}
    box_sizes = []
    bad = []
    for xp in xmls:
        w, h, boxes, fname = parse_xml(xp)
        stem = os.path.splitext(os.path.basename(xp))[0]
        img_path = os.path.join(RAW_DIR, 'IMAGES', fname if fname else stem + '.jpg')
        if not os.path.exists(img_path):
            # 有些 xml 的 filename 与文件名不一致，按 stem 兜底
            img_path = os.path.join(RAW_DIR, 'IMAGES', stem + '.jpg')
        if not os.path.exists(img_path):
            bad.append(('image_missing', xp))
            continue
        lines = []
        for (name, x1, y1, x2, y2) in boxes:
            if name not in CLASSES:
                bad.append(('unknown_class', xp, name))
                continue
            name_counter[name] = name_counter.get(name, 0) + 1
            box_sizes.append((x2 - x1, y2 - y1))
            line = to_yolo_line(CLASSES.index(name), w, h, x1, y1, x2, y2)
            if line:
                lines.append(line)
        if not lines:
            bad.append(('empty_boxes', xp))
            continue
        prefix = stem.split('_')[0]
        group = PREFIX_TO_CLASS.get(prefix, prefix)
        records.append({
            'stem': stem,
            'image': img_path,
            'group': group,
            'lines': lines,
        })

    print('有效样本:', len(records), '| 问题样本:', len(bad), '| 类别框数:', name_counter)
    if bad[:5]:
        print('问题样例:', bad[:5])

    # 分层划分（按 group 分层，保证每类都按比例进入各集合）
    rng = random.Random(SEED)
    by_group = {}
    for r in records:
        by_group.setdefault(r['group'], []).append(r)
    splits = {'train': [], 'val': [], 'test': []}
    for g, items in sorted(by_group.items()):
        rng.shuffle(items)
        n = len(items)
        n_train = int(round(n * SPLIT_RATIO[0]))
        n_val = int(round(n * SPLIT_RATIO[1]))
        for i, it in enumerate(items):
            if i < n_train:
                splits['train'].append(it)
            elif i < n_train + n_val:
                splits['val'].append(it)
            else:
                splits['test'].append(it)
        print('  %-18s total=%3d train=%3d val=%3d test=%3d' % (
            g, n, len([x for x in items[:n_train]]), len([x for x in items[n_train:n_train + n_val]]), len([x for x in items[n_train + n_val:]])))

    # 输出
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    for split in ('train', 'val', 'test'):
        os.makedirs(os.path.join(OUT_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(OUT_DIR, 'labels', split), exist_ok=True)
        for r in splits[split]:
            shutil.copy2(r['image'], os.path.join(OUT_DIR, 'images', split, os.path.basename(r['image'])))
            with open(os.path.join(OUT_DIR, 'labels', split, r['stem'] + '.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(r['lines']) + '\n')

    data_yaml = os.path.join(OUT_DIR, 'data.yaml')
    with open(data_yaml, 'w', encoding='utf-8') as f:
        f.write('# NEU-DET YOLO dataset (auto-generated)\n')
        f.write('path: %s\n' % OUT_DIR.replace('\\', '/'))
        f.write('train: images/train\n')
        f.write('val: images/val\n')
        f.write('test: images/test\n')
        f.write('nc: %d\n' % len(CLASSES))
        f.write('names:\n')
        for i, c in enumerate(CLASSES):
            f.write('  %d: %s\n' % (i, c))

    import statistics
    meta = {
        'source': 'NEU surface defect database (NEU-DET), Northeastern University',
        'raw_dir': RAW_DIR,
        'classes': CLASSES,
        'class_box_counts': name_counter,
        'num_images': len(records),
        'num_boxes': sum(len(r['lines']) for r in records),
        'split_counts': {k: len(v) for k, v in splits.items()},
        'split_ratio': SPLIT_RATIO,
        'seed': SEED,
        'image_size': [200, 200],
        'box_w_h_mean': [round(statistics.mean(x[0] for x in box_sizes), 1), round(statistics.mean(x[1] for x in box_sizes), 1)],
        'box_w_h_min': [min(x[0] for x in box_sizes), min(x[1] for x in box_sizes)],
        'box_w_h_max': [max(x[0] for x in box_sizes), max(x[1] for x in box_sizes)],
        'problems': bad[:20],
        'citation': [
            'K. Song and Y. Yan, Applied Surface Science, vol.285, pp.858-864, 2013.',
            'Y. He, K. Song, Q. Meng, Y. Yan, IEEE TIM, 69(4), 1493-1504, 2020.',
        ],
    }
    with open(os.path.join(OUT_DIR, 'data_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print('\n输出目录:', OUT_DIR)
    print('data.yaml:', data_yaml)
    print('split:', meta['split_counts'])


if __name__ == '__main__':
    main()
