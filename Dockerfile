FROM python:3.11-slim

WORKDIR /app

# 安装依赖（chromadb/sentence-transformers 需要的编译工具链）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 模型文件较大，单独一层便于利用构建缓存
COPY models ./models
COPY . .

RUN mkdir -p data/chroma data/samples

EXPOSE 8000 8501

# 具体启动哪个服务由 docker-compose 的 command 覆盖
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
