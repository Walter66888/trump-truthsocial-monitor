import os
import requests
import json
import time
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
import sqlite3
from datetime import datetime
import logging
import traceback

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 环境变量配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.environ.get("LINE_GROUP_ID")

# 验证环境变量
if not DEEPSEEK_API_KEY:
    logger.error("未设置 DEEPSEEK_API_KEY 环境变量")
    raise ValueError("必须设置 DEEPSEEK_API_KEY 环境变量")
    
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error("未设置 LINE_CHANNEL_ACCESS_TOKEN 环境变量")
    raise ValueError("必须设置 LINE_CHANNEL_ACCESS_TOKEN 环境变量")
    
if not LINE_GROUP_ID:
    logger.error("未设置 LINE_GROUP_ID 环境变量")
    raise ValueError("必须设置 LINE_GROUP_ID 环境变量")

# Truth Social URL
TRUTH_URL = "https://truthsocial.com/@realDonaldTrump"

# 设置日志顶部
def log_startup():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 50)
    logger.info(f"脚本启动时间: {current_time}")
    logger.info("=" * 50)

# 脚本结束时的日志
def log_shutdown():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 50)
    logger.info(f"脚本结束时间: {current_time}")
    logger.info("=" * 50)

# 初始化数据库
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
    logger.info("数据库初始化完成")

# 检查贴文是否已存在
def is_post_exists(post_id):
    conn = sqlite3.connect('posts.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# 保存新贴文
def save_post(post_id, content):
    conn = sqlite3.connect('posts.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (post_id, content, created_at) VALUES (?, ?, ?)",
        (post_id, content, datetime.now())
    )
    conn.commit()
    conn.close()
    logger.info(f"保存贴文 ID: {post_id}")

# 配置 Selenium
def setup_selenium():
    logger.info("设置 Selenium")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    
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

# 尝试使用虚拟浏览器技术爬取
def scrape_truth_social():
    logger.info("开始爬取 Truth Social")
    
    driver = None
    
    try:
        driver = setup_selenium()
        
        # 添加随机用户代理
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36'
        ]
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": random.choice(user_agents)})
        
        # 访问页面
        driver.get(TRUTH_URL)
        logger.info("已访问 Truth Social 页面")
        
        # 等待较长时间确保页面完全加载
        logger.info("等待页面加载...")
        time.sleep(10)
        
        try:
            # 尝试获取页面源代码
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # 尝试各种选择器
            post_elements = []
            selectors = [
                'article', 
                'div.status-card', 
                'div.status-wrapper', 
                'div.post', 
                'div.truth'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    logger.info(f"找到 {len(elements)} 个匹配 '{selector}' 的元素")
                    post_elements = elements
                    break
            
            if not post_elements:
                # 备用方案：尝试找任何可能的贴文
                post_candidates = soup.find_all('div', class_=lambda c: c and ('post' in c.lower() or 'status' in c.lower() or 'truth' in c.lower()))
                if post_candidates:
                    logger.info(f"找到 {len(post_candidates)} 个可能的贴文元素")
                    post_elements = post_candidates
            
            if not post_elements:
                logger.warning("无法找到任何贴文元素")
                
                # 最后尝试：获取使用 AJAX 加载的内容
                try:
                    logger.info("尝试通过直接 API 请求获取贴文...")
                    
                    # 尝试使用 requests 直接获取 API 数据
                    api_url = f"https://truthsocial.com/api/v1/accounts/realDonaldTrump/statuses"
                    headers = {
                        'User-Agent': random.choice(user_agents),
                        'Accept': 'application/json'
                    }
                    
                    response = requests.get(api_url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        if data and len(data) > 0:
                            latest_truth = data[0]
                            content = latest_truth.get('content', '')
                            
                            # 清理 HTML 标签
                            content_soup = BeautifulSoup(content, 'html.parser')
                            clean_content = content_soup.get_text()
                            
                            post_id = str(latest_truth.get('id'))
                            
                            # 获取媒体 URL
                            media_urls = []
                            media_attachments = latest_truth.get('media_attachments', [])
                            for media in media_attachments:
                                url = media.get('url')
                                if url:
                                    media_urls.append(url)
                            
                            logger.info(f"通过 API 获取到贴文，ID: {post_id}")
                            return {
                                'id': post_id,
                                'content': clean_content,
                                'media_urls': media_urls
                            }
                    
                    logger.warning(f"API 请求失败或没有数据: {response.status_code}")
                except Exception as e:
                    logger.error(f"API 请求失败: {e}")
                
                return None
            
            # 获取最新的贴文
            latest_post = post_elements[0]
            
            # 尝试提取文本内容
            content = None
            content_selectors = [
                'div.status-content', 
                'div.status-body', 
                'div.post-content', 
                'p', 
                'div.text'
            ]
            
            for selector in content_selectors:
                element = latest_post.select_one(selector)
                if element:
                    content = element.get_text(strip=True)
                    logger.info(f"使用选择器 '{selector}' 找到内容")
                    break
            
            if not content:
                # 如果找不到特定元素，尝试提取所有文本
                content = latest_post.get_text(separator=' ', strip=True)
                logger.info("使用整个元素的文本作为内容")
            
            if not content:
                logger.warning("无法提取贴文内容")
                return None
            
            # 生成唯一ID
            post_id = hashlib.md5(content.encode()).hexdigest()
            
            # 查找媒体
            media_urls = []
            for img in latest_post.find_all('img'):
                src = img.get('src')
                if src and not src.endswith(('.svg', '.ico')):
                    if not src.startswith(('http://', 'https://')):
                        src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                    media_urls.append(src)
            
            for video in latest_post.find_all('video'):
                src = video.get('src')
                if src:
                    if not src.startswith(('http://', 'https://')):
                        src = f"https://truthsocial.com{src}" if src.startswith('/') else f"https://truthsocial.com/{src}"
                    media_urls.append(src)
            
            logger.info(f"找到贴文，ID: {post_id}, 媒体数量: {len(media_urls)}")
            return {
                'id': post_id,
                'content': content,
                'media_urls': media_urls
            }
            
        except Exception as e:
            logger.error(f"处理页面时出错: {e}")
            logger.error(traceback.format_exc())
            return None
            
    except Exception as e:
        logger.error(f"爬取失败: {e}")
        logger.error(traceback.format_exc())
        return None
        
    finally:
        if driver:
            driver.quit()
            logger.info("Selenium driver 已关闭")

# 使用 DeepSeek API 翻译内容
def translate_with_deepseek(text):
    logger.info("使用 DeepSeek API 翻译")
    
    try:
        # 使用 OpenAI SDK 的方式来调用 DeepSeek API
        from openai import OpenAI
        
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业翻译，请将以下英文文本翻译成中文。保持原意，使语言流畅自然。"},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            stream=False
        )
        
        translated_text = response.choices[0].message.content
        logger.info("翻译完成")
        return translated_text
        
    except Exception as e:
        logger.error(f"翻译失败: {e}")
        logger.error(traceback.format_exc())
        return f"[翻译错误] 原文: {text}"

# 内容分析（判断是文字还是视频）
def analyze_content(post):
    if not post:
        return None
        
    # 检查是否包含视频
    is_video = any(url.endswith(('.mp4', '.avi', '.mov', '.webm')) for url in post.get('media_urls', []))
    
    # 翻译文本内容
    translated_content = translate_with_deepseek(post['content'])
    
    result = {
        'id': post['id'],
        'original_content': post['content'],
        'translated_content': translated_content,
        'media_urls': post['media_urls'],
        'is_video': is_video
    }
    
    content_type = "影片" if is_video else "文字"
    logger.info(f"内容类型: {content_type}")
    
    return result

# 发送消息到 LINE 群组
def send_to_line_group(message):
    logger.info(f"发送消息到 LINE 群组: {message[:50]}...")
    
    if not LINE_CHANNEL_ACCESS_TOKEN:
        error = "ERROR: LINE_CHANNEL_ACCESS_TOKEN 未设置"
        logger.error(error)
        return False
        
    if not LINE_GROUP_ID:
        error = "ERROR: LINE_GROUP_ID 未设置"
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
        
        # 输出详细响应
        logger.info(f"LINE API 响应状态码: {response.status_code}")
        logger.info(f"LINE API 响应内容: {response.text}")
        
        response.raise_for_status()
        logger.info("LINE 消息发送成功")
        return True
    except Exception as e:
        logger.error(f"LINE 消息发送失败: {e}")
        logger.error(traceback.format_exc())
        return False

# 主流程
def main():
    try:
        log_startup()
        
        # 第一次启动时发送通知，用于确认机器人正常工作
        first_run_file = "first_run_completed.txt"
        first_run = not os.path.exists(first_run_file)
        
        if first_run:
            send_to_line_group("🤖 Trump 监控机器人首次启动，正在检查 Truth Social...")
        
        # 初始化数据库
        init_db()
        
        # 爬取最新贴文
        latest_post = scrape_truth_social()
        
        if not latest_post:
            if first_run:
                send_to_line_group("🔍 首次爬取没有找到任何贴文，可能是网页结构变化或者爬虫问题。")
            return
            
        # 只在首次运行时发送爬取结果通知
        if first_run:
            post_info = f"✅ 首次爬取成功！找到贴文！\n\nID: {latest_post['id']}\n\n内容: {latest_post['content'][:100]}...\n\n媒体数量: {len(latest_post['media_urls'])}"
            send_to_line_group(post_info)
            # 标记首次运行已完成
            with open(first_run_file, "w") as f:
                f.write("completed")
        
        # 检查贴文是否已存在
        if is_post_exists(latest_post['id']):
            logger.info(f"贴文 {latest_post['id']} 已存在，跳过处理")
            return  # 静默跳过，不发送通知
        
        # 检查是否为影片贴文
        is_video = any(url.endswith(('.mp4', '.avi', '.mov', '.webm')) for url in latest_post.get('media_urls', []))
        
        if is_video:
            # 静默略过影片贴文，但仍然保存到数据库
            logger.info("检测到影片贴文，略过处理")
            save_post(latest_post['id'], latest_post['content'])
            return
            
        # 分析并翻译内容（不发送进度通知）
        logger.info("开始分析并翻译内容")
        processed_content = analyze_content(latest_post)
        
        if not processed_content:
            logger.error("内容处理失败")
            return  # 处理失败，静默跳过
            
        # 构建 LINE 消息
        message = f"🔔 Trump 在 Truth Social 有新动态！\n\n📝 类型: 文字\n\n🇺🇸 原文:\n{processed_content['original_content']}\n\n🇹🇼 中文翻译:\n{processed_content['translated_content']}"
        
        # 如果有媒体但不是视频，附加媒体 URL
        if processed_content['media_urls']:
            message += "\n\n🖼️ 媒体链接:\n" + "\n".join(processed_content['media_urls'])
        
        # 发送到 LINE 群组
        logger.info("准备发送消息到 LINE 群组")
        if send_to_line_group(message):
            # 保存已处理的贴文
            save_post(processed_content['id'], processed_content['original_content'])
            logger.info("处理完成，贴文已保存")
        
    except Exception as e:
        logger.error(f"执行过程中出错: {str(e)}")
        logger.error(traceback.format_exc())
        # 只在首次运行时发送错误通知
        if first_run:
            error_message = f"❌ 首次执行过程中出错: {str(e)}"
            send_to_line_group(error_message)
    finally:
        log_shutdown()

if __name__ == "__main__":
    main()
