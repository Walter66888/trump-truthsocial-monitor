FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装 Chrome 和其他依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制程序代码
COPY app.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium:/usr/local/bin:${PATH}"

# 设置启动命令
CMD ["python", "app.py"]
