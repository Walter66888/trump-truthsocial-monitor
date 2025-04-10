FROM python:3.10-slim

# 設置工作目錄
WORKDIR /app

# 安裝 Chrome、ChromeDriver 和其他依賴
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# 手動下載與安裝最新的 ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}') \
    && CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip

# 清理不需要的包
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# 複製依賴文件與安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY app.py .

# 設置環境變數
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV PATH="/usr/local/bin:${PATH}"

# 設置啟動命令
CMD ["python", "app.py"]
