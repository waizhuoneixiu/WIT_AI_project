# -*- coding: utf-8 -*-
"""把 Kaggle GC10-DET zip 转成 YOLO 10 类检测数据集（支持 VOC XML / 已有 txt）。"""
import json
import os
import random
import shutil
import zipfile
import xml.etree.ElementTree as ET

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
RAW = os.path.join(PROJ, 'data', 'raw')
ZIP = os.path.join(RAW, 'gc10_kaggle.zip')
EXTRACT = os.path.join(RAW, 'gc10_kaggle')
OUT = os.path.join(PROJ, 'data', 'gc10_yolo')
IMGS = ('.jpg', '.jpeg', '.png', '.bmp')


def parse_voc(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find('size')
    w = int(float(size.findtext('width'))) if size is not None else 0
    h = int(float(size.findtext('height'))) if size is not None else 0
    fn = root.findtext('filename') or ''
    objs = []
    for obj in root.findall('object'):
        name = (obj.findtext('name') or '').strip()
        bb = obj.find('bndbox')
        if not bb:
            continue
        try:
            x1 = float(bb.findtext('xmin')); y1 = float(bb.findtext('ymin'))
            x2 = float(bb.findtext('xmax')); y2 = float(bb.findtext('ymax'))
        except Exception:
            continue
        objs.append((name, x1, y1, x2, y2))
    return fn, w, h, objs


def main():
    if not os.path.exists(ZIP):
        raise SystemExit('missing zip: ' + ZIP)
    os.makedirs(EXTRACT, exist_ok=True)
    print('extracting ...', flush=True)
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(EXTRACT)
    xmls, imgs = [], []
    for r, _, fs in os.walk(EXTRACT):
        for f in fs:
            p = os.path.join(r, f); low = f.lower()
            if low.endswith('.xml'):
                xmls.append(p)
            elif low.endswith(IMGS):
                imgs.append(p)
    print('xml:', len(xmls), 'images:', len(imgs), flush=True)
    img_by_name, img_by_stem = {}, {}
    for p in imgs:
        img_by_name[os.path.basename(p)] = p
        img_by_stem.setdefault(os.path.splitext(os.path.basename(p))[0], []).append(p)

    samples = []
    names = set()
    for xp in xmls:
        try:
            fn, w, h, objs = parse_voc(xp)
        except Exception:
            continue
        ip = img_by_name.get(fn)
        if not ip:
            cand = img_by_stem.get(os.path.splitext(os.path.basename(xp))[0]) or []
            ip = cand[0] if cand else None
        if not ip:
            continue
        if not w or not h:
            try:
                from PIL import Image
                with Image.open(ip) as im:
                    w, h = im.size
            except Exception:
                continue
        lines = []
        for name, x1, y1, x2, y2 in objs:
            if not name:
                continue
            names.add(name)
            x1 = max(0.0, min(w, x1)); x2 = max(0.0, min(w, x2))
            y1 = max(0.0, min(h, y1)); y2 = max(0.0, min(h, y2))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            lines.append((name, ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h)))
        if lines:
            samples.append((ip, lines))
    names = sorted(names)
    print('classes:', names, flush=True)
    print('samples:', len(samples), flush=True)
    if not names or not samples:
        raise SystemExit('no valid annotations')
    ci = {n: i for i, n in enumerate(names)}

    # 按主类分层
    rng = random.Random(0)
    groups = {}
    for ip, lines in samples:
        groups.setdefault(lines[0][0], []).append((ip, lines))
    train, val = [], []
    for name, arr in groups.items():
        rng.shuffle(arr)
        nv = max(1, int(len(arr) * 0.2)) if len(arr) >= 5 else 0
        val += arr[:nv]
        train += arr[nv:]
    rng.shuffle(train); rng.shuffle(val)
    print('train/val:', len(train), len(val), flush=True)

    for split in ('train', 'val'):
        os.makedirs(os.path.join(OUT, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(OUT, 'labels', split), exist_ok=True)
    used = set()
    for split, arr in (('train', train), ('val', val)):
        for ip, lines in arr:
            stem = os.path.splitext(os.path.basename(ip))[0]
            name = stem; k = 1
            while name in used:
                name = '%s_%d' % (stem, k); k += 1
            used.add(name)
            ext = os.path.splitext(ip)[1].lower() or '.jpg'
            dst = os.path.join(OUT, 'images', split, name + ext)
            try:
                os.link(ip, dst)
            except Exception:
                shutil.copy2(ip, dst)
            with open(os.path.join(OUT, 'labels', split, name + '.txt'), 'w', encoding='utf-8') as f:
                for cname, (cx, cy, bw, bh) in lines:
                    f.write('%d %.6f %.6f %.6f %.6f\n' % (ci[cname], cx, cy, bw, bh))
    with open(os.path.join(OUT, 'data.yaml'), 'w', encoding='utf-8') as f:
        f.write('path: %s\n' % OUT.replace('\\', '/'))
        f.write('train: images/train\nval: images/val\nnc: %d\nnames: %s\n' % (len(names), json.dumps(names, ensure_ascii=False)))
    print('saved:', OUT, flush=True)


if __name__ == '__main__':
    main()
