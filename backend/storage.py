# -*- coding: utf-8 -*-
"""SQLite 持久化：批次/图片/原始预测/任务/复核/分析/聊天/报告。

所有数据保存在 config.DEV 下的 storage/ 目录，可用环境变量 STEELSCAN_DB 覆盖。
"""
import json
import os
import sqlite3
import threading
import time
import uuid

import config

STORAGE_DIR = os.environ.get('STEELSCAN_STORAGE_DIR', os.path.join(config.DEV, 'storage'))
IMAGES_DIR = os.path.join(STORAGE_DIR, 'images')
DB_PATH = os.environ.get('STEELSCAN_DB', os.path.join(STORAGE_DIR, 'steelscan.db'))

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id TEXT PRIMARY KEY,
    batch_no TEXT NOT NULL,
    workpiece_no TEXT,
    image_path TEXT NOT NULL,
    annotated_path TEXT,
    width INTEGER,
    height INTEGER,
    model_version TEXT,
    timing_json TEXT,
    review_status TEXT DEFAULT 'pending',
    review_version INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS detections (
    detection_id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    class_id INTEGER,
    class_name TEXT,
    score REAL,
    bbox_json TEXT,
    raw_json TEXT,
    order_idx INTEGER
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    inspection_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    result_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id TEXT NOT NULL,
    review_status TEXT NOT NULL,
    reviewer TEXT,
    payload_json TEXT,
    base_version INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id TEXT NOT NULL,
    content_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_type TEXT,
    context_id TEXT,
    question TEXT,
    answer TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    inspection_id TEXT,
    format TEXT,
    content TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_inspections_batch ON inspections(batch_no);
CREATE INDEX IF NOT EXISTS idx_detections_inspection ON detections(inspection_id);
"""


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def new_id(prefix):
    return '%s-%s-%s' % (prefix, time.strftime('%Y%m%d%H%M%S'), uuid.uuid4().hex[:6].upper())


def get_conn():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with _lock, get_conn() as conn:
        conn.executescript(SCHEMA)


def insert_inspection(inspection_id, batch_no, workpiece_no, image_path, annotated_path,
                      width, height, model_version, timing):
    with _lock, get_conn() as conn:
        conn.execute(
            'INSERT INTO inspections (inspection_id,batch_no,workpiece_no,image_path,annotated_path,'
            'width,height,model_version,timing_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (inspection_id, batch_no, workpiece_no, image_path, annotated_path, width, height,
             model_version, json.dumps(timing, ensure_ascii=False), now()))


def insert_detections(inspection_id, defects):
    with _lock, get_conn() as conn:
        for i, d in enumerate(defects):
            score = d.get('confidence', d.get('score', 0))
            conn.execute(
                'INSERT INTO detections (detection_id,inspection_id,class_id,class_name,score,'
                'bbox_json,raw_json,order_idx) VALUES (?,?,?,?,?,?,?,?)',
                (d.get('detection_id') or new_id('DET'), inspection_id, d['class_id'],
                 d['class_name'], score, json.dumps(d['bbox_xyxy']),
                 json.dumps(d, ensure_ascii=False), i))


def insert_task(task_id, type_, status, inspection_id=None, result=None, error=None):
    ts = now()
    with _lock, get_conn() as conn:
        conn.execute(
            'INSERT INTO tasks (task_id,type,status,inspection_id,created_at,updated_at,result_json,error)'
            ' VALUES (?,?,?,?,?,?,?,?)',
            (task_id, type_, status, inspection_id, ts, ts,
             json.dumps(result, ensure_ascii=False) if result is not None else None, error))


def get_task(task_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get('result_json'):
        d['result'] = json.loads(d['result_json'])
    for k in ('created_at', 'updated_at'):
        d.setdefault(k, None)
    return d


def get_inspection(inspection_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM inspections WHERE inspection_id=?', (inspection_id,)).fetchone()
        if not row:
            return None, []
        dets = [dict(r) for r in conn.execute(
            'SELECT * FROM detections WHERE inspection_id=? ORDER BY order_idx', (inspection_id,))]
    return row, dets


def list_inspections(batch_no=None, class_id=None, review_status=None, page=1, page_size=20):
    sql = 'SELECT DISTINCT i.* FROM inspections i'
    args = []
    if class_id is not None:
        sql += ' JOIN detections d ON d.inspection_id=i.inspection_id'
    wheres = []
    if batch_no:
        wheres.append('i.batch_no=?')
        args.append(batch_no)
    if class_id is not None:
        wheres.append('d.class_id=?')
        args.append(int(class_id))
    if review_status:
        wheres.append('i.review_status=?')
        args.append(review_status)
    if wheres:
        sql += ' WHERE ' + ' AND '.join(wheres)
    sql += ' ORDER BY i.created_at DESC LIMIT ? OFFSET ?'
    args += [page_size, (page - 1) * page_size]
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, args)]
        total = conn.execute('SELECT COUNT(*) FROM inspections').fetchone()[0]
    return rows, total


def add_review(inspection_id, review_status, reviewer, payload, base_version):
    with _lock, get_conn() as conn:
        row = conn.execute('SELECT review_version FROM inspections WHERE inspection_id=?',
                           (inspection_id,)).fetchone()
        if not row:
            return None, 'not_found'
        current = row['review_version']
        if base_version is not None and int(base_version) != int(current):
            return None, 'version_conflict'
        conn.execute('INSERT INTO reviews (inspection_id,review_status,reviewer,payload_json,'
                     'base_version,created_at) VALUES (?,?,?,?,?,?)',
                     (inspection_id, review_status, reviewer,
                      json.dumps(payload, ensure_ascii=False), current, now()))
        conn.execute('UPDATE inspections SET review_status=?, review_version=review_version+1 '
                     'WHERE inspection_id=?', (review_status, inspection_id))
    return current + 1, None


def get_latest_review(inspection_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM reviews WHERE inspection_id=? ORDER BY id DESC LIMIT 1',
                           (inspection_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d['payload'] = json.loads(d['payload_json']) if d.get('payload_json') else None
    return d


def add_analysis(inspection_id, content):
    with _lock, get_conn() as conn:
        conn.execute('INSERT INTO analyses (inspection_id,content_json,created_at) VALUES (?,?,?)',
                     (inspection_id, json.dumps(content, ensure_ascii=False), now()))


def add_chat(context_type, context_id, question, answer):
    with _lock, get_conn() as conn:
        conn.execute('INSERT INTO chats (context_type,context_id,question,answer,created_at) VALUES (?,?,?,?,?)',
                     (context_type, context_id, question, answer, now()))


def save_report(report_id, inspection_id, fmt, content):
    with _lock, get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO reports (id,inspection_id,format,content,created_at) VALUES (?,?,?,?,?)',
                     (report_id, inspection_id, fmt, content, now()))


def get_report(report_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM reports WHERE id=?', (report_id,)).fetchone()
    return dict(row) if row else None


def batch_summary(batch_no):
    with get_conn() as conn:
        insp = [dict(r) for r in conn.execute('SELECT * FROM inspections WHERE batch_no=?', (batch_no,))]
        if not insp:
            return None
        ids = [r['inspection_id'] for r in insp]
        qmarks = ','.join('?' * len(ids))
        dets = [dict(r) for r in conn.execute(
            'SELECT * FROM detections WHERE inspection_id IN (%s)' % qmarks, ids)]
    per_class = {}
    for d in dets:
        k = d['class_name']
        per_class[k] = per_class.get(k, 0) + 1
    review_stats = {}
    for r in insp:
        review_stats[r['review_status']] = review_stats.get(r['review_status'], 0) + 1
    return {
        'batch_no': batch_no,
        'image_count': len(insp),
        'model_box_count': len(dets),
        'per_class': per_class,
        'review_stats': review_stats,
        'confirmed_count': review_stats.get('confirmed', 0) + review_stats.get('corrected', 0),
        'unresolved_count': review_stats.get('unresolved', 0),
    }
