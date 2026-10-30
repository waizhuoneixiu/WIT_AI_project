#!/usr/bin/env bash
# 本地/Linux 启动后端。
# 用法：
#   PORT=8000 STEELSCAN_API_KEY=my-key bash deploy/run_server.sh
set -e
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
echo "目录: $(pwd)  端口: $PORT"
if [ -n "${STEELSCAN_API_KEY:-}" ]; then echo "API Key: 已启用"; else echo "API Key: 未启用（仅内网使用）"; fi
exec python server.py --host 0.0.0.0 --port "$PORT"
