# -*- coding: utf-8 -*-
"""把 NEU-DET 的 train+val 重新按 80/20 分层划分，生成 data/neu_det_plus（test 保持不变）。"""
import os
import random
import shutil

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
SRC = os.path.join(PROJ, 'data', 'neu_det')
OUT = os.path.join(PROJ, 'data', 'neu_det_plus')
NAMES = ['rolled-in_scale', 'patches', 'crazing', 'pitted_surface', 'inclusion', 'scratches']


def collect(split):
    out = []
    for kind in ['images', 'labels']:
        d = os.path.join(SRC, kind, split)
        for f in sorted(os.listdir(d)):
            if kind == 'images' and f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                out.append(os.path.join(d, f))
    return out


def main():
    imgs_train = collect('train')
    imgs_val = collect('val')
    all_imgs = imgs_train + imgs_val
    print('train+val images:', len(all_imgs))
    # 合并后的清单：以图片路径为键，确保标签存在
    items = []
    for p in all_imgs:
        stem = os.path.splitext(os.path.basename(p))[0]
        # 标签路径：把 \images\<split>\ 替换为 \labels\<split>\
        lab = p.replace(os.sep + 'images' + os.sep, os.sep + 'labels' + os.sep)
        lab = os.path.splitext(lab)[0] + '.txt'
        if os.path.exists(lab):
            items.append((p, lab))
    print('with labels:', len(items))
    rng = random.Random(0)
    # 按类别分层：用标签里的第一个类别做近似分层（纯背景会跳过）
    buckets = {}
    for p, lab in items:
        cls = None
        for line in open(lab, encoding='utf-8', errors='ignore'):
            parts = line.strip().split()
            if parts:
                cls = parts[0]
                break
        buckets.setdefault(cls, []).append((p, lab))
    train, val = [], []
    for cls, arr in buckets.items():
        rng.shuffle(arr)
        n_val = max(1, int(len(arr) * 0.1))
        val += arr[:n_val]
        train += arr[n_val:]
    rng.shuffle(train)
    rng.shuffle(val)
    print('train:', len(train), '| val:', len(val))

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for split in ('train', 'val'):
        os.makedirs(os.path.join(OUT, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(OUT, 'labels', split), exist_ok=True)
    for split, arr in (('train', train), ('val', val)):
        for p, lab in arr:
            name = os.path.basename(p)
            dst_img = os.path.join(OUT, 'images', split, name)
            try:
                os.link(p, dst_img)
            except Exception:  # noqa: BLE001
                shutil.copy2(p, dst_img)
            shutil.copy2(lab, os.path.join(OUT, 'labels', split, name.rsplit('.', 1)[0] + '.txt'))
    with open(os.path.join(OUT, 'data.yaml'), 'w', encoding='utf-8') as f:
        f.write('path: %s\n' % OUT.replace('\\', '/'))
        f.write('train: images/train\nval: images/val\ntest: %s\n' %
                os.path.join(SRC, 'images', 'test').replace('\\', '/'))
        f.write('nc: 6\nnames: %s\n' % NAMES)
    print('saved:', OUT)


if __name__ == '__main__':
    main()

