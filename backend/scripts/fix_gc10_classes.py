# -*- coding: utf-8 -*-
"""清洗 GC10 原始标注里的拼写错误类：12 类 -> 标准 10 类。"""
import json
import os
from collections import Counter

PROJ = r'D:\Users\何ch\source\repos  AI\AIvision1'
DATA = os.path.join(PROJ, 'data', 'gc10_yolo')
YAML = os.path.join(DATA, 'data.yaml')

CANON = ['1_chongkong', '2_hanfeng', '3_yueyawan', '4_shuiban', '5_youban',
         '6_siban', '7_yiwu', '8_yahen', '9_zhehen', '10_yaozhe']
NAME_MAP = {'10_yaozhed': '10_yaozhe'}


def main():
    # 读取当前 names
    raw = {}
    txt = open(YAML, encoding='utf-8').read()
    for line in txt.splitlines():
        if line.strip().startswith('names:'):
            raw = json.loads(line.split('names:', 1)[1].strip())
            break
    print('current names:', raw)
    idx_to_name = {i: n for i, n in enumerate(raw) if isinstance(n, str)}
    canon_idx = {n: i for i, n in enumerate(CANON)}
    # 统计 + 重写
    counts = Counter()
    dropped = 0
    changed = 0
    for split in ('train', 'val'):
        ld = os.path.join(DATA, 'labels', split)
        for fn in os.listdir(ld):
            if not fn.endswith('.txt'):
                continue
            p = os.path.join(ld, fn)
            out = []
            for line in open(p, encoding='utf-8'):
                parts = line.split()
                if len(parts) < 5:
                    continue
                cid = int(parts[0])
                name = idx_to_name.get(cid)
                if name == 'd':
                    dropped += 1
                    continue
                name = NAME_MAP.get(name, name)
                if name not in canon_idx:
                    dropped += 1
                    continue
                counts[name] += 1
                if cid != canon_idx[name]:
                    changed += 1
                out.append('%d %s' % (canon_idx[name], ' '.join(parts[1:5])))
            with open(p, 'w', encoding='utf-8') as f:
                f.write('\n'.join(out) + ('\n' if out else ''))
    print('boxes:', sum(counts.values()), '| per class:', dict(counts))
    print('changed ids:', changed, '| dropped boxes:', dropped)
    with open(YAML, 'w', encoding='utf-8') as f:
        f.write('path: %s\n' % DATA.replace('\\', '/'))
        f.write('train: images/train\nval: images/val\nnc: %d\nnames: %s\n' % (len(CANON), json.dumps(CANON, ensure_ascii=False)))
    print('updated:', YAML)


if __name__ == '__main__':
    main()
