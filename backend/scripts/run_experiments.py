# -*- coding: utf-8 -*-
"""实验矩阵：顺序训练 + 自动评测（后台无人值守运行）。

每个实验的日志写入 runs/logs/<name>.log，评测 JSON 写入 runs/eval_<name>.json。
可用 `python scripts/run_experiments.py --only n320` 只跑单个实验。
"""
import argparse
import json
import os
import subprocess
import sys
import time

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TRAIN = os.path.join(DEV, 'scripts', 'train.py')
EVAL = os.path.join(DEV, 'scripts', 'evaluate.py')
LOGS = os.path.join(DEV, 'runs', 'logs')
os.makedirs(LOGS, exist_ok=True)

EXPERIMENTS = [
    dict(name='n320', model='yolo26n.pt', imgsz=320, epochs=150, batch=16, workers=4, extra=[]),
    dict(name='n320_pw', model='yolo26n.pt', imgsz=320, epochs=100, batch=16, workers=4,
         extra=['--cls-pw', '0.5']),
    dict(name='n640', model='yolo26n.pt', imgsz=640, epochs=120, batch=8, workers=4, extra=[]),
    # s640 依赖 yolo26s.pt 下载，如已就绪可放开（由 lead 视下载情况决定）
]


def run(cmd, log_path):
    t0 = time.time()
    print('\n[%s] RUN: %s' % (time.strftime('%H:%M:%S'), ' '.join(cmd)), flush=True)
    with open(log_path, 'a', encoding='utf-8', errors='ignore') as f:
        f.write('\n\n===== %s =====\n%s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), ' '.join(cmd)))
        f.flush()
        p = subprocess.run(cmd, cwd=DEV, stdout=f, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    print('[%s] exit=%s elapsed=%.0fs log=%s' % (time.strftime('%H:%M:%S'), p.returncode, dt, log_path), flush=True)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    todo = [e for e in EXPERIMENTS if not args.only or e['name'] == args.only]
    print('experiments:', [e['name'] for e in todo], flush=True)

    summary = []
    for e in todo:
        name = e['name']
        log = os.path.join(LOGS, name + '.log')
        cmd = [PY, TRAIN, '--name', name, '--model', e['model'], '--imgsz', str(e['imgsz']),
               '--epochs', str(e['epochs']), '--batch', str(e['batch']), '--workers', str(e['workers'])] + e['extra']
        rc = run(cmd, log)
        weights = os.path.join(DEV, 'runs', name, 'weights', 'best.pt')
        item = {'name': name, 'train_rc': rc, 'weights': weights, 'weights_exists': os.path.exists(weights)}
        if rc == 0 and os.path.exists(weights):
            out = os.path.join(DEV, 'runs', 'eval_%s.json' % name)
            cmd2 = [PY, EVAL, '--weights', weights, '--imgsz', str(e['imgsz']), '--device', '0', '--out', out]
            rc2 = run(cmd2, log)
            item['eval_rc'] = rc2
            item['eval_json'] = out
        summary.append(item)
        print('[%s] SUMMARY: %s' % (time.strftime('%H:%M:%S'), json.dumps(item, ensure_ascii=False)), flush=True)

    print('\nALL DONE', flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
