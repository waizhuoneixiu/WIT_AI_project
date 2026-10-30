# SteelScan 缺陷检测后端（CPU 版 Docker 镜像）
# 构建：docker build -t steelscan-api:1.1 .
# 运行：docker run -p 8000:8000 -e STEELSCAN_API_KEY=your-key steelscan-api:1.1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# OpenCV 运行库（Debian slim 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装 CPU 版 torch，避免默认拉取 CUDA 大包（约 2GB）
RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 \
        --index-url https://download.pytorch.org/whl/cpu

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# 拷贝代码与权重（data/runs/docs 已在 .dockerignore 中排除）
COPY . .

ENV STEELSCAN_API_KEY=""
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5)"

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8000"]
