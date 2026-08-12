# -------- Build Stage --------
FROM python:3.11-slim AS builder
WORKDIR /app

# 只装编译必需的轻量包（gcc 就够了，不需要整个 build-essential）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# 先装 CPU 版 torch，避免 sentence-transformers 拉 2GB CUDA 包
RUN pip install --no-cache-dir --user torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --user -r requirements.txt \
    -i http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

# -------- Runtime Stage --------
FROM python:3.11-slim
WORKDIR /app

# libgomp1 是 sentence-transformers / torch 的运行时依赖
# fonts-dejavu-core 提供验证码所需的 TTF 字体
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制代码
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 创建数据目录（运行时用 volume 挂载覆盖）
RUN mkdir -p ./backend/data/models ./backend/data/chroma ./backend/data/logs

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
