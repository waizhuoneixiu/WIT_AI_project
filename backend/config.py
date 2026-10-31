# -*- coding: utf-8 -*-
"""AIvision1 竞赛项目全局配置。"""
import os

DEV = os.path.dirname(os.path.abspath(__file__))


def load_dotenv_if_present():
    """Load private settings before reading them; explicit environment values win."""
    path = os.path.join(DEV, '.env')
    if os.path.isfile(path):
        from dotenv import load_dotenv
        load_dotenv(path, override=False)


load_dotenv_if_present()

# ---------- 数据 ----------
DATA_DIR = os.path.join(DEV, 'data', 'neu_det')
DATA_YAML = os.path.join(DATA_DIR, 'data.yaml')
CLASSES = ['rolled-in_scale', 'patches', 'crazing', 'pitted_surface', 'inclusion', 'scratches']
CLASSES_CN = {
    'rolled-in_scale': '氧化铁皮压入',
    'patches': '斑块',
    'crazing': '龟裂',
    'pitted_surface': '麻点/凹坑',
    'inclusion': '夹杂',
    'scratches': '划伤',
}

# ---------- 模型 ----------
MODELS_DIR = os.path.join(DEV, 'models')
PRETRAINED = os.path.join(MODELS_DIR, 'yolo26n.pt')       # 预训练权重
# 最终选型：YOLO26n @ imgsz=640（n640 实验，测试集综合最优）
BEST_WEIGHTS = os.path.join(DEV, 'runs', 'n640', 'weights', 'best.pt')
RUNS_DIR = os.path.join(DEV, 'runs')
DEFAULT_IMGSZ = 640
DEFAULT_CONF = 0.25
DEFAULT_IOU = 0.45
DEFAULT_DEVICE = 0  # 0=GPU, 'cpu'=CPU
DETECTOR_PROVIDER = os.environ.get('DETECTOR_PROVIDER', 'modelscope').strip().lower()
MODELSCOPE_BASE_URL = os.environ.get(
    'MODELSCOPE_BASE_URL',
    'https://studio-waizhuoneixiu-steelscan-demo.api-inference.modelscope.net').rstrip('/')
MODELSCOPE_API_TOKEN = os.environ.get('MODELSCOPE_API_TOKEN', '').strip()
MODELSCOPE_TIMEOUT = float(os.environ.get('MODELSCOPE_TIMEOUT', '60'))

# ---------- 报告 ----------
REPORTS_DIR = os.path.join(DEV, 'reports')
KNOWLEDGE_DIR = os.path.join(DEV, 'agent', 'knowledge')

# ---------- 大模型（从 .env / 环境变量读取，不写死密钥） ----------
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'deepseek')  # deepseek / openai / mock
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_VLM_MODEL = os.environ.get('OPENAI_VLM_MODEL', 'gpt-4o-mini')

# 低置信度阈值：低于该值的检测框交给 VLM/人工复核
LOW_CONF_THRESHOLD = float(os.environ.get('LOW_CONF_THRESHOLD', '0.45'))
# 业务判定阈值：单图存在任一缺陷且置信度 >= 该值 => NG
NG_CONF_THRESHOLD = float(os.environ.get('NG_CONF_THRESHOLD', '0.25'))

# ---------- 后端安全 ----------
# /api、/detect、/model/info 与图片共用业务鉴权；留空仅用于本机调试。
API_KEY = os.environ.get('STEELSCAN_API_KEY', '')
