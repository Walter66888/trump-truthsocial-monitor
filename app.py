import os
import requests
import json
import time
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
import sqlite3
from datetime import datetime
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境變數配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.environ.get("LINE_GROUP_ID")

# 驗證環境變數
if not DEEPSEEK_API_KEY:
    logger.error("未設置 DEEPSEEK_API_KEY 環境變數")
    raise ValueError("必須設置 DEEPSEEK_API_KEY 環境變數")
    
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error("未設置 LINE_CHANNEL_ACCESS_TOKEN 環境變數")
    raise ValueError("必須設置 LINE_CHANNEL_ACCESS_TOKEN 環境變數")
    
if not LINE_GROUP_ID:
    logger.error("未設置 LINE_GROUP_ID 環境變數")
    raise ValueError("必須設置 LINE_GROUP_ID 環境變數")

# Truth Social URL
TRUTH_URL = "https://truthsocial.com/@realDonaldTrump"

# 設置日誌頂部
def log_startup():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 50)
    logger.info(f"腳本啟動時間: {current_time}")
    logger.info("=" * 50)

# 腳本結束時的日誌
def log_shutdown():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 50)
    logger.info(f"腳本結束時間: {current_time}")
    logger.info("=" * 50)

# 初始化數據庫
def init_db():
    conn = sqlite3.connect('posts.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        post_id TEXT PRIMARY KEY,
        content TEXT,
        created_at TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
    logger.info("數據庫初始化完成")

# 檢查貼文是否已存在
def is_post_exists(post_id):
    conn = sqlite3.connect('posts.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# 保存新貼文
def save_post(post_id, content):
    conn = sqlite3.connect('posts.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (post_id, content, created_at) VALUES (?, ?, ?)",
        (post_id, content, datetime.now())
    )
    conn.commit()
    conn.close()
    logger.info(f"保存貼文 ID: {post_id}")

# 配置 Selenium
def setup_selenium():
    logger.info("设置 Selenium")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # 使用系统安装的 Chromium
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    chrome_options.binary_location = chrome_bin
    
    # 使用系统安装的 chromedriver
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("成功使用系统 chromedriver 建立 driver")
        return driver
    except Exception as e:
        logger.error(f"建立 driver 失败: {e}")
        raise
        
# 爬取 Truth Social 貼文
def scrape_truth_social():
    logger.info("開始爬取 Truth Social")
    
    driver = None
    
    try:
        driver = setup_selenium()
        
        # 添加隨機用戶代理
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36 Edg/92.0.902.84',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0'
        ]
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": random.choice(user_agents)})
        
        # 訪問頁面
        driver.get(TRUTH_URL)
        logger.info("已訪問 Truth Social 頁面")
        
        # 等待較長時間確保頁面完全加載
        try:
            logger.info("等待頁面元素加載...")
            # 嘗試多種可能的選擇器
            selectors = ["article.status-card", "div.status-wrapper", ".truth-social-post", ".post-content", ".timeline-item", "article", "div.post"]
            
            for selector in selectors:
                try:
                    logger.info(f"嘗試選擇器: {selector}")
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"選擇器 {selector} 成功找到元素")
                    break
                except:
                    logger.info(f"選擇器 {selector} 未找到元素")
                    continue
            
            # 添加更長的等待時間
            logger.info("等待頁面完全加載...")
            time.sleep(10)
            
            # 截取屏幕截圖以便診斷
            driver.save_screenshot("truthsocial_screenshot.png")
            logger.info("已保存頁面截圖")
            
            # 獲取所有頁面內容進行分析
            page_source = driver.page_source
            
            # 將頁面源代碼保存到文件中以便分析
            with open("truthsocial_page.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            logger.info("已保存頁面源代碼")
            
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # 嘗試尋找任何可能的貼文容器元素
            all_articles = soup.find_all('article')
            all_divs_with_post = soup.find_all('div', class_=lambda x: x and ('post' in x.lower() or 'truth' in x.lower() or 'status' in x.lower()))
            
            logger.info(f"找到 {len(all_articles)} 個 article 元素")
            logger.info(f"找到 {len(all_divs_with_post)} 個疑似貼文的 div 元素")
            
            # 尋找最新的貼文
            posts = []
            
            # 嘗試多種可能的選擇器
            for selector in ['article.status-card', 'div.status-wrapper', '.truth-social-post', '.post-content', '.timeline-item', 'article', 'div.post']:
                posts = soup.select(selector)
                if posts:
                    logger.info(f"使用選擇器 '{selector}' 找到 {len(posts)} 個貼文")
                    break
            
            if not posts and all_articles:
                posts = all_articles
                logger.info(f"使用所有 article 元素作為備用")
            
            if not posts and all_divs_with_post:
                posts = all_divs_with_post
                logger.info(f"使用可能的貼文 div 元素作為備用")
            
            if not posts:
                logger.warning("沒有找到任何可能的貼文元素")
                return None
            
            latest_post = posts[0]
            logger.info("找到最新貼文")
            
            # 提取貼文內容（嘗試多種方法）
            content = None
            
            # 方法 1: 直接找内容元素
            content_selectors = ['div.status-content', 'div.status-body', '.post-content', '.truth-content', 'p', '.text']
            for selector in content_selectors:
                content_element = latest_post.select_one(selector)
                if content_element:
                    content = content_element.text.strip()
                    logger.info(f"使用選擇器 '{selector}' 找到貼文內容")
                    break
            
            # 方法 2: 如果沒找到特定内容元素，使用整個貼文的文本
            if not content:
                content = latest_post.get_text(separator=' ', strip=True)
                logger.info("使用整個貼文的文本作為內容")
            
            if not content:
                logger.warning("無法提取貼文內容")
                return None
                
            # 生成貼文 ID
            post_id = hashlib.md5(content.encode()).hexdigest()
            
            # 檢查是否有媒體
            media_urls = []
            
            # 尋找所有圖片和視頻元素
            for img in latest_post.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src and not src.endswith(('.svg', '.ico')):
                    if not src.startswith(('http://', 'https://')):
                        src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                    media_urls.append(src)
                    
            for video in latest_post.find_all('video'):
                src = video.get('src') or video.get('data-src')
                if src:
                    if not src.startswith(('http://', 'https://')):
                        src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                    media_urls.append(src)
            
            logger.info(f"貼文 ID: {post_id}, 媒體數量: {len(media_urls)}")
            return {
                'id': post_id,
                'content': content,
                'media_urls': media_urls
            }
            
        except Exception as e:
            logger.error(f"處理頁面內容時出錯: {e}")

# 使用 DeepSeek API 翻譯內容
def translate_with_deepseek(text):
    logger.info("使用 DeepSeek API 翻譯")
    
    try:
        # 使用 OpenAI SDK 的方式來呼叫 DeepSeek API
        from openai import OpenAI
        
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一個專業翻譯，請將以下英文文本翻譯成中文。保持原意，使語言流暢自然。"},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            stream=False
        )
        
        translated_text = response.choices[0].message.content
        logger.info("翻譯完成")
        return translated_text
        
    except Exception as e:
        logger.error(f"翻譯失敗: {e}")
        return f"[翻譯錯誤] 原文: {text}"

# 內容分析（判斷是文字還是視頻）
def analyze_content(post):
    if not post:
        return None
        
    # 檢查是否包含視頻
    is_video = any(url.endswith(('.mp4', '.avi', '.mov', '.webm')) for url in post.get('media_urls', []))
    
    # 翻譯文本內容
    translated_content = translate_with_deepseek(post['content'])
    
    result = {
        'id': post['id'],
        'original_content': post['content'],
        'translated_content': translated_content,
        'media_urls': post['media_urls'],
        'is_video': is_video
    }
    
    content_type = "影片" if is_video else "文字"
    logger.info(f"內容類型: {content_type}")
    
    return result

# 發送消息到 LINE 群組
def send_to_line_group(message):
    logger.info(f"發送消息到 LINE 群組: {message[:50]}...")
    
    if not LINE_CHANNEL_ACCESS_TOKEN:
        error = "ERROR: LINE_CHANNEL_ACCESS_TOKEN 未設置"
        logger.error(error)
        return False
        
    if not LINE_GROUP_ID:
        error = "ERROR: LINE_GROUP_ID 未設置"
        logger.error(error)
        return False
    
    url = 'https://api.line.me/v2/bot/message/push'
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': LINE_GROUP_ID,
        'messages': [
            {
                'type': 'text',
                'text': message
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        
        # 輸出詳細回應
        logger.info(f"LINE API 響應狀態碼: {response.status_code}")
        logger.info(f"LINE API 響應內容: {response.text}")
        
        response.raise_for_status()
        logger.info("LINE 消息發送成功")
        return True
    except Exception as e:
        logger.error(f"LINE 消息發送失敗: {e}")
        return False

# 主流程
def main():
    try:
        log_startup()
        
        # 第一次啟動時發送通知，用於確認機器人正常工作
        first_run_file = "first_run_completed.txt"
        first_run = not os.path.exists(first_run_file)
        
        if first_run:
            send_to_line_group("🤖 Trump 監控機器人首次啟動，正在檢查 Truth Social...")
        
        # 初始化數據庫
        init_db()
        
        # 爬取最新貼文
        latest_post = scrape_truth_social()
        
        if not latest_post:
            if first_run:
                send_to_line_group("🔍 首次爬取沒有找到任何貼文，可能是網頁結構變化或者爬蟲問題。")
            return
            
        # 只在首次運行時發送爬取結果通知
        if first_run:
            post_info = f"✅ 首次爬取成功！找到貼文！\n\nID: {latest_post['id']}\n\n內容: {latest_post['content'][:100]}...\n\n媒體數量: {len(latest_post['media_urls'])}"
            send_to_line_group(post_info)
            # 標記首次運行已完成
            with open(first_run_file, "w") as f:
                f.write("completed")
        
        # 檢查貼文是否已存在
        if is_post_exists(latest_post['id']):
            logger.info(f"貼文 {latest_post['id']} 已存在，跳過處理")
            return  # 靜默跳過，不發送通知
        
        # 檢查是否為影片貼文
        is_video = any(url.endswith(('.mp4', '.avi', '.mov', '.webm')) for url in latest_post.get('media_urls', []))
        
        if is_video:
            # 靜默略過影片貼文，但仍然保存到數據庫
            logger.info("檢測到影片貼文，略過處理")
            save_post(latest_post['id'], latest_post['content'])
            return
            
        # 分析並翻譯內容（不發送進度通知）
        logger.info("開始分析並翻譯內容")
        processed_content = analyze_content(latest_post)
        
        if not processed_content:
            logger.error("內容處理失敗")
            return  # 處理失敗，靜默跳過
            
        # 構建 LINE 消息
        message = f"🔔 Trump 在 Truth Social 有新動態！\n\n📝 類型: 文字\n\n🇺🇸 原文:\n{processed_content['original_content']}\n\n🇹🇼 中文翻譯:\n{processed_content['translated_content']}"
        
        # 如果有媒體但不是視頻，附加媒體 URL
        if processed_content['media_urls']:
            message += "\n\n🖼️ 媒體連結:\n" + "\n".join(processed_content['media_urls'])
        
        # 發送到 LINE 群組
        logger.info("準備發送消息到 LINE 群組")
        if send_to_line_group(message):
            # 保存已處理的貼文
            save_post(processed_content['id'], processed_content['original_content'])
            logger.info("處理完成，貼文已保存")
        
    except Exception as e:
        logger.error(f"執行過程中出錯: {str(e)}")
        # 只在首次運行時發送錯誤通知
        if first_run:
            error_message = f"❌ 首次執行過程中出錯: {str(e)}"
            send_to_line_group(error_message)
    finally:
        log_shutdown()

if __name__ == "__main__":
    main()
