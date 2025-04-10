import os
import requests
import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
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

# 配置 Selenium
def setup_selenium():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    if os.environ.get('RENDER'):
        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome-stable")
        chrome_options.binary_location = chrome_bin
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# 爬取 Truth Social 貼文
def scrape_truth_social():
    logger.info("開始爬取 Truth Social")
    
    driver = None
    
    try:
        driver = setup_selenium()
        driver.get(TRUTH_URL)
        
        # 等待頁面加載
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.status-card, div.status-wrapper"))
        )
        
        # 確保頁面完全加載
        time.sleep(5)
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # 尋找最新的貼文
        posts = soup.select('article.status-card, div.status-wrapper')
        
        if not posts:
            logger.warning("沒有找到貼文")
            return None
        
        latest_post = posts[0]
        
        # 提取貼文內容
        content_element = latest_post.select_one('div.status-content, div.status-body')
        if not content_element:
            logger.warning("找不到貼文內容元素")
            return None
            
        content = content_element.text.strip()
        
        # 生成貼文 ID
        post_id = hashlib.md5(content.encode()).hexdigest()
        
        # 檢查是否有媒體
        media = latest_post.select('div.media-gallery img, div.media-gallery video, div.media-attachment img, div.media-attachment video')
        media_urls = []
        
        for item in media:
            src = item.get('src') or item.get('data-src')
            if src:
                if not src.startswith(('http://', 'https://')):
                    src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                media_urls.append(src)
        
        return {
            'id': post_id,
            'content': content,
            'media_urls': media_urls
        }
        
    except Exception as e:
        logger.error(f"爬取失敗: {e}")
        return None
    
    finally:
        if driver:
            driver.quit()

# 使用 DeepSeek API 翻譯內容
def translate_with_deepseek(text):
    logger.info("使用 DeepSeek API 翻譯")
    
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一個專業翻譯，請將以下英文文本翻譯成中文。保持原意，使語言流暢自然。"},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        translated_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
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
# 主流程
def main():
    try:
        # 發送啟動通知
        send_to_line_group("🤖 Trump 監控機器人已啟動，正在檢查 Truth Social...")
        
        # 初始化數據庫
        init_db()
        
        # 爬取最新貼文
        latest_post = scrape_truth_social()
        
        if not latest_post:
            message = "🔍 沒有找到任何貼文，可能是網頁結構變化或者爬蟲問題。"
            send_to_line_group(message)
            return
            
        # 發送爬取結果通知
        post_info = f"✅ 找到貼文！\n\nID: {latest_post['id']}\n\n內容: {latest_post['content'][:100]}...\n\n媒體數量: {len(latest_post['media_urls'])}"
        send_to_line_group(post_info)
            
        # 檢查是否為新貼文
        if is_post_exists(latest_post['id']):
            send_to_line_group("🔄 該貼文已處理過，跳過翻譯和推送。")
            return
            
        # 分析並翻譯內容
        send_to_line_group("🔄 正在分析並翻譯內容...")
        processed_content = analyze_content(latest_post)
        
        if not processed_content:
            send_to_line_group("❌ 內容處理失敗，可能是 DeepSeek API 問題。")
            return
            
        # 構建 LINE 消息
        content_type = "影片" if processed_content['is_video'] else "文字"
        message = f"🔔 Trump 在 Truth Social 有新動態！\n\n📝 類型: {content_type}\n\n🇺🇸 原文:\n{processed_content['original_content']}\n\n🇹🇼 中文翻譯:\n{processed_content['translated_content']}"
        
        # 如果有媒體，附加媒體 URL
        if processed_content['media_urls']:
            message += "\n\n🖼️ 媒體連結:\n" + "\n".join(processed_content['media_urls'])
        
        # 發送到 LINE 群組
        if send_to_line_group(message):
            # 保存已處理的貼文
            save_post(processed_content['id'], processed_content['original_content'])
            send_to_line_group("✅ 處理完成，貼文已保存。")
        
    except Exception as e:
        error_message = f"❌ 執行過程中出錯: {str(e)}"
        logger.error(error_message)
        send_to_line_group(error_message)
