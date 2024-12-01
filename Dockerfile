# Build in local: docker build . --platform linux/arm64 -t rsstranslator/rsstranslator:dev
# Run with docker-compose to test: docker-compose -f docker-compose.test.yml up -d
# Push to dev: docker push rsstranslator/rsstranslator:dev
# Run with docker-compose in dev: docker-compose -f docker-compose.dev.yml up -d
# Multi-arch build:
# docker buildx create --use
# docker buildx build . --platform linux/arm64,linux/amd64 --push -t rsstranslator/rsstranslator:latest -t rsstranslator/rsstranslator:version

FROM python:3.12-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    DockerHOME=/home/rsstranslator

# 安装系统依赖和编译工具
RUN apt-get update && apt-get install -y \
    gettext \
    procps \
    git \
    nodejs \
    curl \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${POETRY_HOME}/bin:$PATH"

WORKDIR $DockerHOME

# 复制项目文件
COPY pyproject.toml poetry.lock ./

# 重新生成 lock 文件并安装依赖
RUN poetry lock --no-update && \
    poetry install --without dev

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p $DockerHOME/data

# 初始化服务器
RUN python manage.py init_server && \
    find $DockerHOME -type d -name "__pycache__" -exec rm -r {} + && \
    rm -rf $DockerHOME/.cache/pip

# 健康检查
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=20s \
    CMD pgrep -f "python manage.py run_huey" || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["sh", "-c", "python manage.py init_server && python manage.py run_huey -f & uvicorn config.asgi:application --host 0.0.0.0"]
