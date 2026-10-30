# -*- coding: utf-8 -*-
"""从 ModelScope 下载本地大模型（默认 DeepSeek-R1-Distill-Qwen-1.5B，无需账号/Key）。

用法：
    python scripts/download_local_llm.py                     # 下载到 models/DeepSeek-R1-Distill-Qwen-1.5B
    python scripts/download_local_llm.py --model deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
    python scripts/download_local_llm.py --dest D:/models/xxx
支持断点续传（.part 文件），下载完自动校验大小并打印路径。
"""
import argparse
import json
import os
import sys
import time
import urllib.request

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B'
BASE = 'https://www.modelscope.cn/models/%s/resolve/master/'
FILES = [
    'config.json',
    'generation_config.json',
    'configuration.json',
    'tokenizer.json',
    'tokenizer_config.json',
    'model.safetensors',
]


def download(model_id, dest):
    os.makedirs(dest, exist_ok=True)
    print('模型: %s\n目标: %s' % (model_id, dest))
    base = BASE % model_id
    for name in FILES:
        url = base + name
        path = os.path.join(dest, name)
        part = path + '.part'
        exist = os.path.getsize(path) if os.path.exists(path) else 0
        # 获取远端大小
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}, method='HEAD')
        try:
            remote = int(urllib.request.urlopen(req, timeout=30).headers.get('Content-Length') or 0)
        except Exception:  # noqa: BLE001
            remote = 0
        if exist and remote and exist == remote:
            print('  [skip] %s (%d bytes)' % (name, exist))
            continue
        start = exist if exist and remote and exist < remote else 0
        if start == 0 and os.path.exists(part):
            os.remove(part)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                                   'Range': 'bytes=%d-' % start})
        r = urllib.request.urlopen(req, timeout=120)
        total = remote or int(r.headers.get('Content-Length') or 0) + start
        mode = 'ab' if start else 'wb'
        done = start
        t0 = time.time()
        last = 0
        with open(part, mode) as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if done - last >= 200 * 1024 * 1024 or time.time() - t0 > 20:
                    speed = (done - start) / max(time.time() - t0, 0.001) / 1024 / 1024
                    pct = (100.0 * done / total) if total else 0
                    print('  %s: %.2f%% (%d/%d) %.1f MB/s' % (name, pct, done, total, speed), flush=True)
                    last = done
                    t0 = time.time()
        if remote and os.path.getsize(part) != remote:
            print('  [WARN] %s 大小不符：%d != %d（可重跑续传）' % (name, os.path.getsize(part), remote))
        else:
            os.replace(part, path)
            print('  [done] %s (%d bytes)' % (name, os.path.getsize(path)))
    print('\n全部完成:', dest)
    print('加载方式: transformers AutoModelForCausalLM.from_pretrained(dest)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.environ.get('LOCAL_LLM_MODEL_ID', DEFAULT_MODEL))
    ap.add_argument('--dest', default=os.path.join(DEV, 'models', DEFAULT_MODEL.split('/')[-1]))
    args = ap.parse_args()
    download(args.model, args.dest)
    sys.exit(0)
