#!/bin/bash

# 设置默认的 pip 镜像源
MIRROR_URL=${PIP_MIRROR_URL:-"https://pypi.org/simple"}

# 检查并安装依赖
if [ -f "/dependencies/python-requirements.txt" ]; then
    echo "Dependency file found, starting to install additional dependencies..."
    echo "Using pip mirror: $MIRROR_URL"
    uv pip install --system -r /dependencies/python-requirements.txt -i "$MIRROR_URL"
fi

# 获取超时时间配置，默认为 10000 秒
WORKER_TIMEOUT=${WORKER_TIMEOUT:-10000}

# 启动 FastAPI 应用
exec uvicorn app.main:app --host 0.0.0.0 --port 8194 --timeout-keep-alive $WORKER_TIMEOUT