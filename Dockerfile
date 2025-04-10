FROM python:3.10-slim

# 設置工作目錄
WORKDIR /app

# 安裝 Chrome 和依賴
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 建立 chromedriver 符號連結
RUN ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

# 複製依賴文件與安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY app.py .

# 設置環境變數
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV RENDER=true

# 設置啟動命令
CMD ["python", "app.py"]
