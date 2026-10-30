# -*- coding: utf-8 -*-
"""大模型提示词：质检分析与追问。要求只做辅助解释、不编造根因，输出严格 JSON。"""
import json

ANALYSIS_SYSTEM = (
    '你是热轧带钢表面质检领域的资深工程师，负责对 YOLO 检测结果做辅助分析。'
    '你只能依据给定的检测结果与知识条目进行解释，不得编造未提供的工艺参数、设备故障或根因。'
    '检测结果只代表模型在图像上发现的目标，不代表产品合格/不合格结论；最终判定需人工复核。'
    '请用中文输出严格 JSON（不要输出 Markdown 代码块），字段：'
    'facts（检测事实，字符串数组）、references（知识依据，字符串数组）、'
    'hypotheses（参考原因，必须用"可能/建议核实"等措辞，字符串数组）、'
    'recheck_steps（复检步骤，字符串数组）、missing_information（待补信息，字符串数组）。'
)

CHAT_SYSTEM = (
    '你是热轧带钢表面质检助手，围绕当前检测记录或批次回答用户问题。'
    '只能使用给定的检测记录、批次统计和知识条目作答，不编造原因、规则或数据；'
    '不确定时明确说明缺少哪些信息，并建议人工复核。'
    '请用中文输出严格 JSON（不要输出 Markdown 代码块），字段：'
    'answer（回答文本，字符串）、references（参考的知识/数据依据，字符串数组）。'
)


# 本地小模型（DeepSeek-R1 蒸馏）专用：禁止思考过程，直接给 JSON
LOCAL_ANALYSIS_SYSTEM = (
    '你是JSON生成器。只输出一个JSON对象，不要输出思考过程、解释或Markdown代码块。'
    '字段：facts、references、hypotheses（用可能/建议核实措辞）、recheck_steps、missing_information，'
    '每个字段都是字符串数组。'
)


def build_analysis_compact_prompt(detections, inspection_id=None):
    """精简版分析提示词：只给检测事实 + JSON 模板，避免小模型长篇思考。"""
    lines = ['检测结果（class_id 为团队契约编号）：']
    if not detections:
        lines.append('未检出六类目标缺陷。')
    else:
        for i, d in enumerate(detections, 1):
            lines.append('%d. class_id=%s %s(%s) 置信度=%.4f bbox=%s' % (
                i, d.get('class_id'), d.get('class_name'), d.get('class_cn', ''),
                float(d.get('confidence', d.get('score', 0))), d.get('bbox_xyxy')))
    lines += ['', '请只输出 JSON：',
              '{"facts":["..."],"references":["..."],"hypotheses":["..."],'
              '"recheck_steps":["..."],"missing_information":["..."]}']
    return '\n'.join(lines)


def build_analysis_user_prompt(detections, inspection_id=None, review_status=None):
    lines = ['当前检测记录：%s' % (inspection_id or '(未提供)'),
             '复核状态：%s' % (review_status or 'pending'), '', '检测结果（class_id 为团队契约编号）：']
    if not detections:
        lines.append('未检出六类目标缺陷。')
    else:
        for i, d in enumerate(detections, 1):
            lines.append('%d. class_id=%s, 名称=%s(%s), 置信度=%.4f, bbox_xyxy=%s' % (
                i, d.get('class_id'), d.get('class_name'), d.get('class_cn', ''),
                float(d.get('confidence', d.get('score', 0))), d.get('bbox_xyxy')))
    lines += ['', '可用知识条目（若与缺陷类别匹配才引用；不匹配不要引用）：', _knowledge_text(detections),
              '', '请输出 JSON。']
    return '\n'.join(lines)


def build_chat_user_prompt(context_type, context, question):
    lines = ['上下文类型：%s' % context_type]
    if context_type == 'inspection':
        lines += ['检测记录：%s' % json.dumps(context, ensure_ascii=False)]
    else:
        lines += ['批次统计：%s' % json.dumps(context, ensure_ascii=False)]
    lines += ['', '用户问题：%s' % question, '', '请输出 JSON。']
    return '\n'.join(lines)


KNOWLEDGE = {
    'crazing': {'definition': '龟裂/网状裂纹，细线状、方向不规则。',
                'causes': ['轧制过程温度/变形不均', '材料局部应力集中', '氧化皮去除不彻底'],
                'actions': ['高倍裁剪复核裂纹走向', '结合工艺参数与批次记录排查', '人工复判并记录']},
    'inclusion': {'definition': '非金属夹杂，不规则块状/条状。',
                  'causes': ['炼钢脱氧/精炼不充分', '保护浇注不良', '耐材剥落'],
                  'actions': ['复核尺寸与分布', '关联炉次与连铸参数', '必要时取样化验']},
    'patches': {'definition': '斑块/色差，区域状亮度或纹理异常。',
                'causes': ['局部氧化/酸洗不均', '乳化液或水迹残留', '轧辊状态异常'],
                'actions': ['确认是否影响后续涂镀', '检查轧辊与乳化液', '跟踪同批次相邻卷']},
    'pitted_surface': {'definition': '麻点/凹坑，点状密集。',
                       'causes': ['氧化铁皮压入后脱落', '酸洗不足', '轧辊粘附异物'],
                       'actions': ['复核凹坑密度', '检查除鳞与酸洗工艺', '评估是否降级']},
    'rolled-in_scale': {'definition': '轧入氧化皮，沿轧向条带状/块状。',
                        'causes': ['除鳞压力不足', '炉内氧化严重', '轧制节奏异常'],
                        'actions': ['复核压入深度与连续性', '检查除鳞系统与炉温', '同批次趋势统计']},
    'scratches': {'definition': '划痕，线状、方向性强。',
                  'causes': ['辊道/导板刮擦', '吊运或堆垛摩擦', '设备毛刺'],
                  'actions': ['复核深度与长度', '检查辊道与吊运接触点', '确认是否影响等级']},
}


def _knowledge_text(detections):
    names = []
    for d in detections or []:
        n = d.get('class_name')
        if n and n not in names:
            names.append(n)
    if not names:
        return '（无可匹配知识条目）'
    out = []
    for n in names:
        k = KNOWLEDGE.get(n)
        if k:
            out.append('%s：%s 可能原因：%s；处置：%s' % (
                n, k['definition'], '；'.join(k['causes']), '；'.join(k['actions'])))
    return '\n'.join(out) if out else '（无可匹配知识条目）'
