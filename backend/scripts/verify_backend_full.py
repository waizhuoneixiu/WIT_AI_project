# -*- coding: utf-8 -*-
"""真实 HTTP 端到端验收：启动独立服务进程，按团队契约走完整流程。

覆盖：
  /health /classes /model/info /detect /files
  /api/inspections (创建/列表/详情) /api/tasks /api/analysis /api/chat
  /api/review（版本冲突 409）/api/batches/summary /api/reports
  /api/llm/info、WS /ws/tasks/{task_id}
自动识别分析来源 source（deepseek / rule_fallback）。

用法：
    python scripts/verify_backend_full.py                 # 随机端口 + 开启 API Key 鉴权
    python scripts/verify_backend_full.py --no-auth       # 不鉴权
    python scripts/verify_backend_full.py --port 8123
退出码 0 = 全部通过；报告保存到 reports/verify_backend_<时间>.json
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import requests

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_health(base, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(base + '/health', timeout=2)
            if r.status_code == 200:
                return True, r.json()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return False, None


class Verifier:
    def __init__(self, base, headers, api_key):
        self.base = base
        self.headers = headers
        self.api_key = api_key
        self.failures = []
        self.checks = []
        self.expected_source = 'rule_fallback'

    def check(self, cond, msg, extra=None):
        self.checks.append({'ok': bool(cond), 'msg': msg})
        print(('  [OK] ' if cond else '  [FAIL] ') + msg)
        if not cond:
            self.failures.append(msg)
            if extra:
                print('        ', extra)

    # --- 步骤 ---
    def step_health(self):
        print('\n== /health /classes /model/info ==')
        h = requests.get(self.base + '/health', timeout=10).json()
        self.check(h.get('status') == 'ok', 'health ok')
        self.check(h.get('auth_required') is bool(self.api_key), 'auth_required 与配置一致')
        self.check('llm' in h, 'health 含 llm 状态')
        c = requests.get(self.base + '/classes', timeout=10).json()['classes']
        self.check([x['name'] for x in c] == ['crazing', 'inclusion', 'patches',
                                              'pitted_surface', 'rolled-in_scale', 'scratches'],
                   'classes 为契约顺序')
        mi = requests.get(self.base + '/model/info', headers=self.headers, timeout=60).json()
        self.check(mi.get('imgsz') == 640, 'model imgsz=640')
        self.check(mi.get('weights_file') == 'best.pt', '使用 best.pt')

    def step_detect(self, sample):
        print('\n== /detect（低层检测） ==')
        with open(sample, 'rb') as f:
            r = requests.post(self.base + '/detect', headers=self.headers,
                              files={'image': (os.path.basename(sample), f, 'image/jpeg')}, timeout=60)
        self.check(r.status_code == 200, 'HTTP 200')
        res = r.json()
        self.check('defects' in res, '响应含 defects')
        self.check(res.get('imgsz') == 640, 'imgsz=640')

    def step_full_flow(self, sample, batch):
        print('\n== /api/inspections（上传+检测+落库） ==')
        with open(sample, 'rb') as f:
            r = requests.post(self.base + '/api/inspections', headers=self.headers,
                              files={'image': (os.path.basename(sample), f, 'image/jpeg')},
                              data={'batch_no': batch, 'workpiece_no': 'VERIFY-W1'}, timeout=120)
        self.check(r.status_code == 201, 'HTTP 201（实际 %s）' % r.status_code)
        created = r.json()
        insp = created.get('inspection_id')
        task = created.get('task_id')
        self.check(bool(insp and task), '返回 inspection_id/task_id')

        print('\n== 详情 / 任务 / 列表 ==')
        d = requests.get(self.base + '/api/inspections/%s' % insp, headers=self.headers, timeout=30).json()
        self.check(d.get('image_width') == 200 and d.get('image_height') == 200, '原图尺寸 200x200')
        self.check(len(d.get('detections', [])) >= 1, '至少 1 个检测框')
        det = d['detections'][0]
        self.check({'detection_id', 'class_id', 'class_name', 'score', 'bbox_xyxy'} <= set(det.keys()),
                   '框字段符合契约')
        self.check(isinstance(det['bbox_xyxy'], list) and len(det['bbox_xyxy']) == 4, 'bbox_xyxy 4 值')
        self.check(d.get('review_status') == 'pending', '初始 pending')
        ann = d.get('annotated_url')
        if ann:
            ar = requests.get(self.base + ann, timeout=30)
            self.check(ar.status_code == 200 and len(ar.content) > 0, '标注图可访问')
        t = requests.get(self.base + '/api/tasks/%s' % task, headers=self.headers, timeout=30).json()
        self.check(t.get('status') == 'completed', '检测任务 completed')
        lst = requests.get(self.base + '/api/inspections', headers=self.headers,
                           params={'batch_no': batch}, timeout=30).json()
        self.check(lst.get('total', 0) >= 1, '列表 total >= 1')

        print('\n== 大模型分析 / 追问（自动识别 source） ==')
        a = requests.post(self.base + '/api/inspections/%s/analysis' % insp,
                          headers=self.headers, timeout=180).json()
        analysis = a.get('analysis', {})
        for key in ('facts', 'references', 'hypotheses', 'recheck_steps', 'missing_information'):
            self.check(key in analysis, 'analysis 含 %s' % key)
        source = analysis.get('source')
        self.check(source in ('deepseek', 'local-deepseek', 'rule_fallback'),
                   'analysis source 有效（%s）' % source)
        self.check(source == self.expected_source,
                   'analysis source 与配置一致（期望 %s，实际 %s）' % (self.expected_source, source))
        if self.expected_source == 'rule_fallback':
            self.check('reason' in analysis, '降级带 reason')
        c = requests.post(self.base + '/api/chat/messages', headers=self.headers,
                          json={'context_type': 'inspection', 'context_id': insp,
                                'question': '这类缺陷可能原因是什么？怎么复检？'}, timeout=180).json()
        self.check(bool(c.get('answer')), 'chat 返回 answer')
        self.check(c.get('source') == self.expected_source, 'chat source 与配置一致（%s）' % c.get('source'))
        print('  source =', source, '| model =', analysis.get('model'),
              '| latency_ms =', analysis.get('latency_ms'))

        print('\n== 复核（版本校验） ==')
        r1 = requests.post(self.base + '/api/inspections/%s/review' % insp, headers=self.headers,
                           json={'review_status': 'confirmed', 'reviewer': 'verify-bot',
                                 'notes': '验收复核', 'base_version': 0}, timeout=30)
        self.check(r1.status_code == 200 and r1.json().get('review_version') == 1, '首次复核成功 version=1')
        r2 = requests.post(self.base + '/api/inspections/%s/review' % insp, headers=self.headers,
                           json={'review_status': 'corrected', 'reviewer': 'verify-bot',
                                 'base_version': 0}, timeout=30)
        self.check(r2.status_code == 409, '旧版本复核返回 409')
        r3 = requests.post(self.base + '/api/inspections/%s/review' % insp, headers=self.headers,
                           json={'review_status': 'corrected', 'reviewer': 'verify-bot',
                                 'corrections': [{'detection_id': det['detection_id'], 'class_id': 2}],
                                 'base_version': 1}, timeout=30)
        self.check(r3.status_code == 200, '新版本复核成功')

        print('\n== 批次统计 / 报告 / LLM 状态 ==')
        s = requests.get(self.base + '/api/batches/%s/summary' % batch, headers=self.headers, timeout=30).json()
        self.check(s.get('image_count', 0) >= 1, '批次图片数 >= 1')
        self.check(s.get('model_box_count', 0) >= 1, '批次模型框数 >= 1')
        rep = requests.get(self.base + '/api/reports/%s' % insp, headers=self.headers, timeout=30).json()
        self.check('质检报告' in rep.get('content_md', ''), '报告含标题')
        li = requests.get(self.base + '/api/llm/info', headers=self.headers, timeout=30).json()
        self.check(li.get('configured') == (self.expected_source != 'rule_fallback'),
                   'llm/info configured 与配置一致')
        self.check('api_key' not in json.dumps(li).lower(), 'llm/info 不泄露 Key')
        return insp, task

    def step_ws(self, task):
        print('\n== WS /ws/tasks/{task_id} ==')
        try:
            from websockets.sync.client import connect
            ws_url = self.base.replace('http://', 'ws://').replace('https://', 'wss://')
            with connect(ws_url + '/ws/tasks/%s' % task, additional_headers=self.headers, open_timeout=10) as ws:
                e1 = json.loads(ws.recv(timeout=10))
                e2 = json.loads(ws.recv(timeout=10))
                self.check(e1.get('type') == 'accepted', '收到 accepted 事件')
                self.check(e2.get('type') == 'completed', '收到 completed 事件')
        except Exception as e:  # noqa: BLE001
            self.check(False, 'WebSocket 失败: %r' % e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-auth', action='store_true', help='关闭 API Key 鉴权')
    ap.add_argument('--port', type=int, default=0)
    args = ap.parse_args()

    load_env_file(os.path.join(DEV, '.env'))
    port = args.port or free_port()
    base = 'http://127.0.0.1:%d' % port
    tmp = tempfile.mkdtemp(prefix='steelscan_verify_')
    api_key = '' if args.no_auth else 'verify-key-123'

    env = os.environ.copy()
    env['STEELSCAN_STORAGE_DIR'] = tmp
    env['STEELSCAN_DB'] = os.path.join(tmp, 'verify.db')
    env['YOLO_CONFIG_DIR'] = os.path.join(DEV, '.ultralytics')
    env['MPLCONFIGDIR'] = os.path.join(DEV, '.mpl')
    if api_key:
        env['STEELSCAN_API_KEY'] = api_key
    else:
        env.pop('STEELSCAN_API_KEY', None)
    env['PYTHONIOENCODING'] = 'utf-8'

    sample_dir = os.path.join(DEV, 'data', 'neu_det', 'images', 'test')
    sample = None
    if os.path.isdir(sample_dir):
        names = sorted(n for n in os.listdir(sample_dir) if n.lower().endswith('.jpg'))
        for n in names:
            if n.startswith('patches'):
                sample = os.path.join(sample_dir, n)
                break
        sample = sample or (os.path.join(sample_dir, names[0]) if names else None)
    if not sample:
        print('找不到测试图片，无法验收')
        return 1

    print('启动服务: %s' % ' '.join([sys.executable, 'server.py', '--port', str(port)]))
    print('鉴权: %s | DeepSeek Key: %s | 存储: %s' % (
        '开启' if api_key else '关闭',
        '已配置' if os.environ.get('DEEPSEEK_API_KEY', '').strip() else '未配置（规则降级）',
        tmp))
    log_path = os.path.join(tmp, 'server.log')
    log = open(log_path, 'w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, 'server.py', '--host', '127.0.0.1', '--port', str(port)],
                            cwd=DEV, env=env, stdout=log, stderr=subprocess.STDOUT)
    headers = {'X-API-Key': api_key} if api_key else {}
    v = Verifier(base, headers, api_key)
    try:
        ok, health = wait_health(base)
        if not ok:
            print('服务启动失败，日志：')
            log.flush()
            print(open(log_path, encoding='utf-8', errors='ignore').read()[-2000:])
            return 1
        li = requests.get(base + '/api/llm/info', headers=headers, timeout=30).json()
        v.expected_source = li.get('source') if li.get('configured') else 'rule_fallback'
        print('LLM provider: %s | mode: %s | source: %s' % (
            li.get('provider'), li.get('mode'), v.expected_source))
        v.step_health()
        if api_key:
            print('\n== 鉴权校验 ==')
            r = requests.get(base + '/api/inspections', timeout=10)
            v.check(r.status_code == 401, '无 Key 访问受保护接口返回 401')
            r = requests.get(base + '/api/inspections', headers={**headers, 'X-API-Key': 'wrong'}, timeout=10)
            v.check(r.status_code == 401, '错误 Key 返回 401')
        v.step_detect(sample)
        insp, task = v.step_full_flow(sample, 'VERIFY-BATCH-001')
        v.step_ws(task)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            proc.kill()
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)

    result = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'base_url': base,
        'auth': bool(api_key),
        'deepseek_configured': bool(os.environ.get('DEEPSEEK_API_KEY', '').strip()),
        'checks': v.checks,
        'failures': v.failures,
    }
    os.makedirs(os.path.join(DEV, 'reports'), exist_ok=True)
    out = os.path.join(DEV, 'reports', 'verify_backend_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('\n== 结论 ==')
    if v.failures:
        print('FAILED: %d 项' % len(v.failures))
        for f in v.failures:
            print('  -', f)
        print('报告:', out)
        return 1
    print('全部通过 ✔ (%d 项检查)' % len(v.checks))
    print('报告:', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
