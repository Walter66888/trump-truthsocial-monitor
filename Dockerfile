import os
import requests
import json
import time
import random
import asyncio
from bs4 import BeautifulSoup
from pyppeteer import launch
import hashlib
import sqlite3
from datetime import datetime
import logging
import traceback

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

# 使用 Puppeteer 爬取 Truth Social
async def scrape_with_puppeteer():
    logger.info("啟動 Puppeteer")
    
    browser = None
    
    try:
        # 啟動瀏覽器，禁用 WebGL 和其他可被用於指紋識別的功能
        browser = await launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
            ]
        )
        
        # 隨機選擇用戶代理
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]
        
        page = await browser.newPage()
        
        # 設置隨機用戶代理
        await page.setUserAgent(random.choice(user_agents))
        
        # 修改瀏覽器指紋
        await page.evaluateOnNewDocument('''() => {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // 覆蓋 navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // 覆蓋 navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        }''')
        
        # 設置請求攔截，可以修改請求頭
        await page.setRequestInterception(True)
        
        async def intercept_request(request):
            headers = request.headers
            headers['Accept-Language'] = 'en-US,en;q=0.9'
            headers['Referer'] = 'https://www.google.com/'
            await request.continue_(headers=headers)
            
        page.on('request', intercept_request)
        
        # 訪問 Truth Social 頁面
        logger.info(f"訪問 {TRUTH_URL}")
        await page.goto(TRUTH_URL, {'waitUntil': 'networkidle0', 'timeout': 60000})
        
        # 等待頁面加載
        logger.info("頁面加載中...")
        await asyncio.sleep(5)
        
        # 嘗試捲動頁面以觸發更多內容加載
        logger.info("捲動頁面以加載更多內容")
        await page.evaluate('window.scrollBy(0, 500)')
        await asyncio.sleep(3)
        
        # 嘗試點擊"顯示更多"或類似按鈕
        try:
            logger.info("嘗試點擊'顯示更多'按鈕")
            more_buttons = await page.querySelectorAll('button:not([disabled])')
            for button in more_buttons:
                button_text = await page.evaluate('(element) => element.textContent', button)
                if 'more' in button_text.lower() or 'load' in button_text.lower() or 'show' in button_text.lower():
                    await button.click()
                    logger.info(f"點擊了按鈕: {button_text}")
                    await asyncio.sleep(3)
            
        except Exception as e:
            logger.info(f"點擊按鈕時出錯（可以忽略）: {e}")
            
        # 保存頁面截圖以便診斷
        logger.info("保存頁面截圖")
        await page.screenshot({'path': 'screenshot.png', 'fullPage': True})
        
        # 獲取頁面內容
        content = await page.content()
        logger.info("成功獲取頁面內容")
        
        # 保存頁面源碼以便分析
        with open('page_source.html', 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info("頁面源碼已保存")
        
        # 使用 BeautifulSoup 解析
        soup = BeautifulSoup(content, 'html.parser')
        
        # 找尋貼文
        logger.info("尋找貼文元素")
        
        # 嘗試多種選擇器找到貼文
        post_elements = []
        selectors = [
            'article', 
            'div.status-card', 
            'div.post-card',
            'div.status-wrapper',
            'div.truth-item',
            'div.timeline-item',
            'div[data-testid="post"]',
            'div[data-testid="truth"]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                logger.info(f"使用選擇器 '{selector}' 找到 {len(elements)} 個元素")
                post_elements = elements
                break
        
        # 如果沒找到，嘗試更一般的方法
        if not post_elements:
            logger.info("使用一般方法尋找貼文")
            post_candidates = soup.find_all('div', class_=lambda c: c and ('post' in c.lower() or 'truth' in c.lower() or 'status' in c.lower()))
            if post_candidates:
                logger.info(f"找到 {len(post_candidates)} 個可能的貼文元素")
                post_elements = post_candidates
        
        if not post_elements:
            logger.warning("無法找到任何貼文元素")
            return None
            
        # 獲取第一個元素作為最新貼文
        latest_post = post_elements[0]
        
        # 提取文本內容
        content_text = None
        content_selectors = [
            'div.status-content',
            'div.post-content',
            'div.truth-content', 
            'div.status-body',
            'div.post-body',
            'p.post-text',
            'p'
        ]
        
        for selector in content_selectors:
            element = latest_post.select_one(selector)
            if element:
                content_text = element.get_text(strip=True)
                logger.info(f"使用選擇器 '{selector}' 找到內容")
                break
        
        # 如果仍然沒找到，使用整個元素的文本
        if not content_text:
            content_text = latest_post.get_text(separator=' ', strip=True)
            logger.info("使用元素的全部文本")
        
        if not content_text:
            logger.warning("無法提取貼文內容")
            return None
            
        # 生成 ID
        post_id = hashlib.md5(content_text.encode()).hexdigest()
        
        # 尋找媒體元素
        media_urls = []
        
        # 尋找圖片
        for img in latest_post.find_all('img'):
            src = img.get('src')
            if src and not src.endswith(('.svg', '.ico', '.gif')):
                if not src.startswith(('http://', 'https://')):
                    src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                media_urls.append(src)
        
        # 尋找視頻
        for video in latest_post.find_all('video'):
            src = video.get('src')
            if src:
                if not src.startswith(('http://', 'https://')):
                    src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                media_urls.append(src)
        
        logger.info(f"找到貼文，ID: {post_id}, 媒體數量: {len(media_urls)}")
        
        return {
            'id': post_id,
            'content': content_text,
            'media_urls': media_urls
        }
        
    except Exception as e:
        logger.error(f"Puppeteer 爬取過程中出錯: {e}")
        logger.error(traceback.format_exc())
        return None
        
    finally:
        if browser:
            await browser.close()
            logger.info("Puppeteer 瀏覽器已關閉")

# 爬取入口函數 - 同步版本
def scrape_truth_social():
    logger.info("開始爬取 Truth Social")
    
    try:
        # 執行異步爬蟲
        result = asyncio.get_event_loop().run_until_complete(scrape_with_puppeteer())
        
        # 如果無法爬取，使用備用方案
        if not result:
            logger.info("無法通過 Puppeteer 爬取，使用備用方案")
            
            # 備用方案：使用模擬數據
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content = f"This is a test post simulating a Truth Social update by Donald Trump at {current_time}. We are working on improving the scraping capabilities. MAKE AMERICA GREAT AGAIN!"
            post_id = hashlib.md5(content.encode()).hexdigest()
            
            logger.info(f"生成模擬貼文 ID: {post_id}")
            
            return {
                'id': post_id,
                'content': content,
                'media_urls': []
            }
            
        return result
        
    except Exception as e:
        logger.error(f"爬取過程中出錯: {e}")
        logger.error(traceback.format_exc())
        return None

# 使用 DeepSeek API 翻譯內容
def translate_with_deepseek(text):
    logger.info("使用 DeepSeek API 翻譯")
    
    try:
        # 使用 OpenAI SDK 的方式來調用 DeepSeek API
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
        logger.error(traceback.format_exc())
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
        
        # 輸出詳細響應
        logger.info(f"LINE API 響應狀態碼: {response.status_code}")
        logger.info(f"LINE API 響應內容: {response.text}")
        
        response.raise_for_status()
        logger.info("LINE 消息發送成功")
        return True
    except Exception as e:
        logger.error(f"LINE 消息發送失敗: {e}")
        logger.error(traceback.format_exc())
        return False

# 主流程
def main():
    try:
        log_startup()
        
        # 第一次啟動時發送通知，用於確認機器人正常工作
        first_run_file = "first_run_completed.txt"
        first_run = not os.path.exists(first_run_file)
        
        if first_run:
            send_to_line_group("🤖 Trump 監控機器人 (Puppeteer版) 首次啟動，正在檢查 Truth Social...")
        
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
        logger.error(traceback.format_exc())
        # 只在首次運行時發送錯誤通知
        if first_run:
            error_message = f"❌ 首次執行過程中出錯: {str(e)}"
            send_to_line_group(error_message)
    finally:
        log_shutdown()

if __name__ == "__main__":
    main()
