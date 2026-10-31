# -*- coding: utf-8 -*-
"""团队共同接口（/api）——按仓库 docs/plans/04-shared-contract.md 实现核心流程。

覆盖：
    POST /api/inspections                       上传图片+批次号，检测并落库
    GET  /api/inspections                       历史查询（批次/类别/复核状态分页）
    GET  /api/inspections/{id}                  检测详情（原图坐标框/版本/复核）
    GET  /api/tasks/{task_id}                   任务状态与结果（断线恢复）
    POST /api/inspections/{id}/analysis         生成复检建议（规则模板，可接大模型）
    POST /api/chat/messages                     围绕记录/批次的追问
    POST /api/inspections/{id}/review           人工复核（版本校验）
    GET  /api/batches/{batch_no}/summary        批次真实统计
    GET  /api/reports/{id}                      报告（Markdown）
    WS   /ws/tasks/{task_id}                    任务事件推送（首版：完成后推送一次）
"""
import json
import os
import time

import cv2
import numpy as np
from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     WebSocket, WebSocketDisconnect)
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import contract
import llm
import llm_prompts
import runtime
import review_snapshot
import storage
from config import CLASSES_CN
from security import verify_api_key

router = APIRouter(prefix='/api', dependencies=[Depends(verify_api_key)])
ws_router = APIRouter()
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = ('.jpg', '.jpeg', '.png', '.bmp')

# 缺陷知识（首版内置；后续由队员三提供结构化知识条目替换）
KNOWLEDGE = {
    'crazing': {
        'definition': '龟裂/网状裂纹，细线状、方向不规则，灰度对比弱。',
        'causes': ['轧制过程温度/变形不均', '材料局部应力集中', '表面氧化皮去除不彻底'],
        'actions': ['复核原图高倍裁剪确认裂纹走向与连续性', '结合工艺参数与批次记录排查温度/压下量', '疑似区域人工复判并记录'],
    },
    'inclusion': {
        'definition': '非金属夹杂，呈不规则块状/条状，边界相对清晰。',
        'causes': ['炼钢脱氧/精炼不充分', '连铸保护浇注不良', '耐材剥落'],
        'actions': ['复核夹杂尺寸与分布', '关联炉次与连铸参数', '必要时取样化验确认来源'],
    },
    'patches': {
        'definition': '斑块/色差，区域状亮度或纹理异常，边界模糊。',
        'causes': ['局部氧化/酸洗不均', '乳化液或水迹残留', '轧辊表面状态异常'],
        'actions': ['确认是否影响后续涂镀', '检查轧辊与乳化液状态', '跟踪同批次相邻卷'],
    },
    'pitted_surface': {
        'definition': '麻点/凹坑，点状密集，局部灰度变化明显。',
        'causes': ['氧化铁皮压入后脱落', '酸洗不足', '轧辊粘附异物'],
        'actions': ['复核凹坑密度与深度线索', '检查除鳞与酸洗工艺', '评估是否需降级处理'],
    },
    'rolled-in_scale': {
        'definition': '轧入氧化皮，沿轧向条带状/块状压入。',
        'causes': ['除鳞压力不足', '炉内氧化严重', '轧制节奏异常'],
        'actions': ['复核压入深度与连续性', '检查除鳞系统与炉温', '对同批次做趋势统计'],
    },
    'scratches': {
        'definition': '划痕，线状、方向性强，通常长度明显大于宽度。',
        'causes': ['辊道/导板刮擦', '吊运或堆垛摩擦', '设备毛刺'],
        'actions': ['复核划痕深度与长度', '检查辊道与吊运接触点', '确认是否影响外售等级'],
    },
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _decode(file_bytes):
    if not file_bytes:
        return None
    arr = np.frombuffer(file_bytes, np.uint8)
    try:
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except cv2.error:
        return None


def _annotated(img, defects):
    out = img.copy()
    for d in defects:
        x1, y1, x2, y2 = [int(v) for v in d['bbox_xyxy']]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, '%s %.2f' % (d['class_name'], d['confidence']),
                    (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return out


def _detection_json(d, detection_id=None):
    return {
        'detection_id': detection_id or storage.new_id('DET'),
        'class_id': d['class_id'],
        'class_name': d['class_name'],
        'class_cn': d.get('class_cn', ''),
        'score': round(float(d['confidence']), 4),
        'bbox_xyxy': [round(float(v), 2) for v in d['bbox_xyxy']],
        'area_ratio': d.get('area_ratio'),
    }


def _inspection_summary(row):
    return {
        'inspection_id': row['inspection_id'],
        'batch_no': row['batch_no'],
        'workpiece_no': row['workpiece_no'],
        'image_width': row['width'],
        'image_height': row['height'],
        'model_version': row['model_version'],
        'review_status': row['review_status'],
        'review_version': row['review_version'],
        'created_at': row['created_at'],
        'annotated_url': ('/files/%s' % os.path.basename(row['annotated_path'])) if row['annotated_path'] else None,
    }


def _inspection_detail(row, det_rows):
    detections = []
    for r in det_rows:
        detections.append({
            'detection_id': r['detection_id'],
            'class_id': r['class_id'],
            'class_name': r['class_name'],
            'score': r['score'],
            'bbox_xyxy': json.loads(r['bbox_json']),
        })
    review = row['review']
    corrections = ((review['payload'] or {}).get('corrections') or []) if review else []
    review_invalid = False
    try:
        _, reviewed = review_snapshot.apply_corrections(detections, corrections, row['width'], row['height'])
    except ValueError:
        review_invalid = True
        _, reviewed = review_snapshot.apply_corrections(detections, [], row['width'], row['height'])
    analysis = row['analysis']
    if analysis:
        analysis = dict(analysis, stale=analysis.get('review_version') != row['review_version'])
    return {
        'inspection_id': row['inspection_id'],
        'batch_no': row['batch_no'],
        'workpiece_no': row['workpiece_no'],
        'image_width': row['width'],
        'image_height': row['height'],
        'model_version': row['model_version'],
        'detections': detections,
        'reviewed_detections': reviewed,
        'review_version': row['review_version'],
        'review_invalid': review_invalid,
        'analysis': analysis,
        'timing': json.loads(row['timing_json']) if row['timing_json'] else {},
        'review_status': row['review_status'],
        'review': ({'review_status': review['review_status'], 'reviewer': review['reviewer'],
                    'payload': review['payload'], 'base_version': review['base_version'],
                    'created_at': review['created_at']} if review else None),
        'annotated_url': ('/files/%s' % os.path.basename(row['annotated_path'])) if row['annotated_path'] else None,
        'original_url': '/files/%s' % os.path.basename(row['image_path']),
        'created_at': row['created_at'],
    }


def _rule_analysis(detections, original_detections=None):
    """规则模板兜底：事实/引用/参考原因/复检步骤/待补信息分离输出。"""
    if not detections:
        return {
            'facts': [('当前复核结果无缺陷框，原模型结果另存；不等同于产品合格判定。'
                       if original_detections else '本图未检出六类目标缺陷；不等同于产品合格判定。')],
            'references': [],
            'hypotheses': [],
            'recheck_steps': ['确认拍摄条件（光照/对焦/角度）', '必要时人工目检复核'],
            'missing_information': ['现场光照与拍摄参数', '同批次历史记录'],
        }
    facts = ['检出 %d 处缺陷：' % len(detections)]
    references, hypotheses, steps = [], [], []
    seen = set()
    for d in detections:
        confidence = d.get('confidence', d.get('score'))
        label = '人工修正' if confidence is None else '模型分数 %.2f' % confidence
        facts.append('%s（%s）位于 %s' % (d.get('class_cn') or d['class_name'], label, d['bbox_xyxy']))
        name = d['class_name']
        if name in seen:
            continue
        seen.add(name)
        kb = KNOWLEDGE.get(name, {})
        if kb:
            references.append('%s：%s' % (d['class_cn'], kb['definition']))
            hypotheses += ['%s可能原因：%s' % (d['class_cn'], c) for c in kb.get('causes', [])]
            steps += ['%s：%s' % (d['class_cn'], s) for s in kb.get('actions', [])]
    return {
        'facts': facts,
        'references': references,
        'hypotheses': hypotheses,
        'recheck_steps': steps,
        'missing_information': ['现场光照/拍摄参数', '工艺与批次参数', '人工复判结论'],
    }


def _analysis_detections(detections):
    return [dict(d, class_cn=CLASSES_CN.get(d['class_name'], d['class_name']),
                 confidence=d['score']) for d in detections]


def _analysis_for(detections, inspection_id=None, review_status=None, original_detections=None):
    """优先调用 DeepSeek 大模型；未配置/失败时降级规则模板，并标注来源。"""
    rule = _rule_analysis(detections, original_detections)
    if not llm.available():
        rule['source'] = 'rule_fallback'
        rule['reason'] = '未配置 DEEPSEEK_API_KEY（离线规则模板）'
        return rule
    try:
        try:
            result = llm.chat_json(
                llm_prompts.ANALYSIS_SYSTEM,
                llm_prompts.build_analysis_user_prompt(detections, inspection_id, review_status, original_detections),
            )
        except Exception:
            # 本地小模型在处理长提示词时可能输出截断的思考文本：用精简提示词重试一次
            if llm.source_name() == 'local-deepseek':
                result = llm.chat_json(
                    llm_prompts.LOCAL_ANALYSIS_SYSTEM,
                    llm_prompts.build_analysis_compact_prompt(detections, inspection_id),
                    max_tokens=1200,
                )
            else:
                raise
        data = result.get('data', {})
        out = {}
        for key in ('facts', 'references', 'hypotheses', 'recheck_steps', 'missing_information'):
            val = data.get(key, rule[key])
            if isinstance(val, str):
                val = [val]
            if not isinstance(val, list):
                val = rule[key]
            out[key] = [str(x).strip() for x in val if str(x).strip()][:12]
        out['source'] = llm.source_name()
        out['model'] = result.get('model')
        out['latency_ms'] = result.get('latency_ms')
        out['tokens'] = result.get('tokens')
        return out
    except Exception:  # noqa: BLE001
        rule['source'] = 'rule_fallback'
        rule['reason'] = '大模型调用失败，已降级为规则建议，请稍后重试。'
        return rule


def _rule_answer(context_type, context_id, question, context):
    """规则模板兜底回答（无大模型/失败时使用）。"""
    q = (question or '').strip()
    if context_type == 'batch':
        summary = context
        if not summary:
            return '未找到批次记录：%s' % context_id, []
        base = ('批次 %s 共 %d 张，模型框 %d 个，已复核 %d 张；分类统计：%s。' % (
            context_id, summary['image_count'], summary['model_box_count'],
            summary['confirmed_count'], json.dumps(summary['per_class'], ensure_ascii=False)))
        return base, []
    if context is None:
        return '未找到检测记录：%s' % context_id, []
    detail = context
    if detail['review_invalid']:
        return '旧复核数据无效，请重新复核后获取建议。', []
    det_json = _analysis_detections(detail['reviewed_detections'])
    analysis = _rule_analysis(det_json, detail['detections'])
    if any(k in q for k in ('原因', '为什么', '怎么造成')):
        return '、'.join(analysis['hypotheses']) or '暂无足够依据判断原因，建议补充工艺与图像信息。', analysis['references']
    if any(k in q for k in ('怎么办', '处理', '复检', '建议')):
        return '复检步骤：' + '；'.join(analysis['recheck_steps']), analysis['references']
    return ('记录 %s：原模型框 %d 处，当前复核版本 %d 的有效框 %d 处（%s）。%s' % (
        context_id, len(detail['detections']), detail['review_version'], len(det_json),
        '、'.join('%s×%d' % (k, sum(1 for d in det_json if d['class_name'] == k))
                 for k in dict.fromkeys(d['class_name'] for d in det_json)) if det_json else '无',
        '；'.join(analysis['facts'][:2])), analysis['references'])


def _build_chat_context(context_type, context_id):
    """为聊天组装上下文（检测记录或批次统计）。"""
    if context_type == 'batch':
        summary = storage.batch_summary(context_id)
        return summary, None
    row, dets = storage.get_inspection(context_id)
    if not row:
        return None, None
    detail = _inspection_detail(row, dets)
    if detail['review_invalid']:
        raise HTTPException(status_code=409, detail='旧复核数据无效，请重新复核后生成建议')
    return detail, row


def _answer_question(context_type, context_id, question, context):
    """优先 DeepSeek 大模型回答；失败/未配置降级规则模板。返回 (answer, references, source)。"""
    rule_answer, rule_refs = _rule_answer(context_type, context_id, question, context)
    if not llm.available():
        return rule_answer, rule_refs, 'rule_fallback'
    if context is None:
        return rule_answer, rule_refs, 'rule_fallback'
    try:
        # 上下文裁剪，避免超长
        if context_type == 'inspection':
            ctx = {
                'inspection_id': context.get('inspection_id'),
                'batch_no': context.get('batch_no'),
                'image_width': context.get('image_width'),
                'image_height': context.get('image_height'),
                'model_version': context.get('model_version'),
                'review_status': context.get('review_status'),
                'review_version': context.get('review_version'),
                'detections': context.get('detections', [])[:30],
                'reviewed_detections': context.get('reviewed_detections', [])[:30],
                'review': context.get('review'),
            }
        else:
            ctx = context
        result = llm.chat_json(llm_prompts.CHAT_SYSTEM,
                               llm_prompts.build_chat_user_prompt(context_type, ctx, question),
                               max_tokens=900)
        data = result.get('data', {})
        answer = data.get('answer') or rule_answer
        refs = data.get('references') or rule_refs
        if isinstance(refs, str):
            refs = [refs]
        if not isinstance(refs, list):
            refs = rule_refs
        return str(answer), [str(x) for x in refs][:10], llm.source_name()
    except Exception:  # noqa: BLE001
        return rule_answer, rule_refs, 'rule_fallback'


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
@router.get('/llm/info')
def llm_info():
    """大模型配置状态（不返回 Key）。"""
    info = llm.info()
    info['available'] = llm.available()
    return info


@router.get('/class-map')
def class_map():
    """原始训练类别 -> 契约类别映射（App/报告按契约 class_id）。"""
    return {
        'contract_classes': contract.classes(),
        'raw_model_classes': contract.RAW_CLASSES,
        'mapping': [{'raw_index': i, 'raw_name': n,
                     **contract.contract_class(n)} for i, n in enumerate(contract.RAW_CLASSES)],
    }


@router.post('/inspections', status_code=201)
async def create_inspection(
    image: UploadFile = File(...),
    batch_no: str = Form(...),
    workpiece_no: str = Form(default=None),
):
    if not batch_no or not batch_no.strip():
        raise HTTPException(status_code=422, detail='batch_no 不能为空')
    ext = os.path.splitext(image.filename or '')[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail='仅支持 jpg/jpeg/png/bmp')
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail='图片超过 10MB 限制')
    return await run_in_threadpool(_save_detection, data, ext, batch_no.strip(), workpiece_no)


def _save_detection(data, ext, batch_no, workpiece_no):
    img = _decode(data)
    if img is None:
        raise HTTPException(status_code=400, detail='图片无法解码')

    inspection_id = storage.new_id('INSP')
    task_id = storage.new_id('TASK')
    t0 = time.perf_counter()
    result = runtime.get_detector().detect(img)
    total_ms = (time.perf_counter() - t0) * 1000.0

    defects = [_detection_json(d) for d in result['defects']]
    annotated = _annotated(img, result['defects'])
    img_path = os.path.join(storage.IMAGES_DIR, inspection_id + ext)
    ann_path = os.path.join(storage.IMAGES_DIR, inspection_id + '_pred.jpg')
    timing = {'inference_ms': result.get('inference_ms'), 'total_ms': round(total_ms, 2)}
    written_paths = []
    try:
        os.makedirs(storage.IMAGES_DIR, exist_ok=True)
        for path, pixels, suffix in ((img_path, img, ext), (ann_path, annotated, '.jpg')):
            ok, encoded = cv2.imencode(suffix, pixels)
            if not ok:
                raise OSError('图像编码失败')
            with open(path, 'xb') as f:
                written_paths.append(path)
                f.write(encoded.tobytes())
        storage.save_inspection(inspection_id, batch_no, workpiece_no, img_path, ann_path,
                                result['width'], result['height'], result['model'], timing,
                                defects, task_id)
    except Exception:
        for path in written_paths:
            if os.path.isfile(path):
                os.remove(path)
        raise HTTPException(status_code=500, detail='保存检测记录失败，请稍后重试') from None

    return {
        'inspection_id': inspection_id,
        'task_id': task_id,
        'status': 'completed',
        'detection_count': len(defects),
        'image_width': result['width'],
        'image_height': result['height'],
        'model_version': result['model'],
        'timing': timing,
    }


@router.get('/inspections')
def list_inspection(batch_no: str = None, class_id: int = None, review_status: str = None,
                    page: int = 1, page_size: int = 20):
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    rows, total = storage.list_inspections(batch_no, class_id, review_status, page, page_size)
    items = []
    for row in rows:
        item = _inspection_summary(row)
        _, dets = storage.get_inspection(row['inspection_id'])
        item['detection_count'] = len(dets)
        item['classes'] = sorted(set(d['class_name'] for d in dets))
        items.append(item)
    return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


@router.get('/inspections/{inspection_id}')
def get_inspection(inspection_id: str):
    row, dets = storage.get_inspection(inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail='inspection 不存在')
    return _inspection_detail(row, dets)


@router.get('/tasks/{task_id}')
def get_task(task_id: str):
    task = storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail='task 不存在')
    task.pop('result_json', None)
    return task


class AnalysisRequest(BaseModel):
    note: str | None = None


@router.post('/inspections/{inspection_id}/analysis')
def create_analysis(inspection_id: str, req: AnalysisRequest | None = None):
    row, dets = storage.get_inspection(inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail='inspection 不存在')
    detail = _inspection_detail(row, dets)
    if detail['review_invalid']:
        raise HTTPException(status_code=409, detail='旧复核数据无效，请重新复核后生成建议')
    analysis = _analysis_for(_analysis_detections(detail['reviewed_detections']), inspection_id,
                             row['review_status'], detail['detections'])
    analysis['review_version'] = row['review_version']
    analysis['created_at'] = storage.now()
    task_id = storage.new_id('TASK')
    storage.add_analysis(inspection_id, analysis)
    current, _ = storage.get_inspection(inspection_id)
    analysis['stale'] = current['review_version'] != row['review_version']
    storage.insert_task(task_id, 'analysis', 'completed', inspection_id,
                        {'inspection_id': inspection_id, 'analysis': analysis})
    return {'inspection_id': inspection_id, 'task_id': task_id, 'status': 'completed', 'analysis': analysis}


class ChatRequest(BaseModel):
    context_type: str = 'inspection'  # inspection / batch
    context_id: str
    question: str


@router.post('/chat/messages')
def chat(req: ChatRequest):
    if req.context_type not in ('inspection', 'batch'):
        raise HTTPException(status_code=422, detail='context_type 仅支持 inspection/batch')
    context, _ = _build_chat_context(req.context_type, req.context_id)
    used_version = context['review_version'] if context and req.context_type == 'inspection' else None
    answer, references, source = _answer_question(req.context_type, req.context_id, req.question, context)
    current, _ = storage.get_inspection(req.context_id) if used_version is not None else (None, None)
    stale = current is not None and current['review_version'] != used_version
    task_id = storage.new_id('TASK')
    storage.add_chat(req.context_type, req.context_id, req.question, answer)
    storage.insert_task(task_id, 'chat', 'completed', req.context_id if req.context_type == 'inspection' else None,
                        {'answer': answer, 'references': references, 'source': source,
                         'review_version': used_version, 'stale': stale})
    return {'task_id': task_id, 'status': 'completed', 'answer': answer,
            'references': references, 'source': source, 'review_version': used_version, 'stale': stale}


class ReviewRequest(BaseModel):
    review_status: str  # pending / confirmed / corrected / unresolved
    reviewer: str | None = None
    corrections: list | None = None
    notes: str | None = None
    base_version: int = Field(ge=0, strict=True)


@router.post('/inspections/{inspection_id}/review')
def review(inspection_id: str, req: ReviewRequest):
    if req.review_status not in ('pending', 'confirmed', 'corrected', 'unresolved'):
        raise HTTPException(status_code=422, detail='review_status 非法')
    payload = {'corrections': req.corrections, 'notes': req.notes}
    try:
        version, err = storage.add_review(inspection_id, req.review_status, req.reviewer,
                                          payload, req.base_version)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if err == 'not_found':
        raise HTTPException(status_code=404, detail='inspection 不存在')
    if err == 'version_conflict':
        raise HTTPException(status_code=409, detail='版本冲突：请重新获取最新记录后再提交复核')
    return {'inspection_id': inspection_id, 'review_status': req.review_status, 'review_version': version}


@router.get('/batches/{batch_no:path}/summary')
def batch_summary(batch_no: str):
    summary = storage.batch_summary(batch_no)
    if not summary:
        raise HTTPException(status_code=404, detail='批次不存在')
    return summary


@router.get('/reports/{report_or_inspection_id}')
def get_report(report_or_inspection_id: str):
    rep = storage.get_report(report_or_inspection_id)
    if rep:
        return {'report_id': rep['id'], 'inspection_id': rep['inspection_id'],
                'format': rep['format'], 'content_md': rep['content'], 'created_at': rep['created_at'],
                'review_version': rep['review_version']}
    row, dets = storage.get_inspection(report_or_inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail='报告/记录不存在')
    detail = _inspection_detail(row, dets)
    if detail['review_invalid']:
        raise HTTPException(status_code=409, detail='旧复核数据无效，请重新复核后生成报告')
    lines = ['# 质检报告 %s' % row['inspection_id'], '',
             '- 批次号：%s' % row['batch_no'],
             '- 工件号：%s' % (row['workpiece_no'] or '-'),
             '- 模型版本：%s' % row['model_version'],
             '- 检测时间：%s' % row['created_at'],
             '- 复核状态：%s' % row['review_status'],
             '- 复核版本：%d' % row['review_version'], '',
             '## 原模型检测结果', '']
    if dets:
        lines.append('| 类别 | 中文 | 置信度 | bbox |')
        lines.append('| --- | --- | --- | --- |')
        for d in dets:
            lines.append('| %s | %s | %.4f | %s |' % (
                d['class_name'], CLASSES_CN.get(d['class_name'], ''), d['score'], d['bbox_json']))
    else:
        lines.append('未检出六类目标缺陷（不等同于产品合格判定）。')
    lines += ['', '## 当前人工复核结果', '']
    if detail['review']:
        lines += ['- 复核人：%s' % (detail['review']['reviewer'] or '-'),
                  '- 备注：%s' % ((detail['review']['payload'] or {}).get('notes') or '-'), '']
    else:
        lines.append('尚未提交人工复核，以下保留原模型框。')
    lines += ['| 类别 | 来源 | 原模型分数 | bbox |', '| --- | --- | --- | --- |']
    for d in detail['reviewed_detections']:
        lines.append('| %s | %s | %s | %s |' % (
            CLASSES_CN.get(d['class_name'], d['class_name']),
            '人工新增或修改' if d['source'] == 'manual' else '原模型框',
            '-' if d['score'] is None else '%.4f' % d['score'], d['bbox_xyxy']))
    if not detail['reviewed_detections']:
        lines.append('当前复核结果无六类目标缺陷框（不等同于产品合格判定）。')
    analysis = detail['analysis']
    if analysis:
        lines += ['', '## 辅助分析', '', '- 来源：%s' % analysis.get('source', 'unknown'),
                  '- 依据复核版本：%s' % analysis.get('review_version', '未知'),
                  '- 分析状态：%s' % ('已过时，请重新生成' if analysis['stale'] else '对应当前复核版本')]
        for key, label in (('facts', '事实'), ('references', '依据'), ('hypotheses', '参考原因'),
                           ('recheck_steps', '复检步骤'), ('missing_information', '待补信息')):
            lines += ['', '### ' + label, ''] + ['- ' + item for item in analysis.get(key, [])]
    else:
        lines += ['', '## 辅助分析', '', '尚未生成辅助分析。']
    lines += ['', '## 说明', '',
              '- 模型输出为辅助检测结果，需人工复核确认；', '- 边界框不代表真实缺陷尺寸。']
    content = '\n'.join(lines)
    report_id = storage.new_id('RPT')
    storage.save_report(report_id, row['inspection_id'], 'md', content, row['review_version'])
    return get_report(report_id)


@ws_router.websocket('/ws/tasks/{task_id}')
async def ws_task(websocket: WebSocket, task_id: str):
    try:
        verify_api_key(websocket.headers.get('x-api-key'))
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        task = storage.get_task(task_id)
        if not task:
            await websocket.send_json({'task_id': task_id, 'event_id': 1, 'type': 'error',
                                       'data': {'message': 'task 不存在'}})
            await websocket.close()
            return
        await websocket.send_json({'task_id': task_id, 'event_id': 1, 'type': 'accepted', 'data': {}})
        await websocket.send_json({'task_id': task_id, 'event_id': 2, 'type': 'completed',
                                   'data': {'status': task['status'], 'result': task.get('result') or {}}})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
