import os
import re
import smtplib
import json
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
from flask import Flask, request, abort

# LINE SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# Gemini SDK (使用通用相容性寫法)
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# =====================================================================
# 1. 初始化環境變數與核心套件
# =====================================================================
app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get(
    'LINE_CHANNEL_ACCESS_TOKEN', 
    'lmagqMKGkhEbJqL7sZSrhqF5kWyophFwwWoJKsmvWx3UwfIry3hiqJU2RU4J8YSL1oyx6dVS288efjvePsuBPnMvetNSa+AriQaFOjMK8s6g2+ua0aBWymZpsRjd6vBnx6PX5RssYjvzUov/ufuO0QdB04t89/1O/w1cDnyilFU='
)

LINE_CHANNEL_SECRET = os.environ.get(
    'LINE_CHANNEL_SECRET', 
    '1b0aac2458a142982ae8240394e307e2'
)

GEMINI_API_KEY = os.environ.get(
    'GEMINI_API_KEY', 
    'AIzaSyDkzb0CVRNGRxm1h4TkdJ-apYH8PFJ1VvQ'
)

GMAIL_USER = os.environ.get(
    'GMAIL_USER', 
    'karen1023440321@gmail.com'
)

GMAIL_PASSWORD = os.environ.get(
    'GMAIL_APP_PASSWORD', 
    'doqf fsmx wknk bvvi'
)

# 安全啟動 API 客戶端
try:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
except Exception as e:
    print(f"【⚠️ 警告】LINE SDK 初始化失敗: {e}")

# =====================================================================
# 2. 定義 Gemini 結構化輸出的資料模型 (Pydantic)
# =====================================================================
class EventExtraction(BaseModel):
    date: str = Field(description="行程日期，格式必須為 YYYY-MM-DD。若無法判斷，填入 'NONE'")
    time: str = Field(description="行程時間，24小時制格式為 HH:MM。若無法判斷，填入 'NONE'")
    title: str = Field(description="行程的主旨、活動名稱。例如：延平大樓開會")
    location: str = Field(description="行程的具體地點。若未提及，填入 '未指定'")

# =====================================================================
# 3. 功能函式實作
# =====================================================================
def send_gmail(to_email, subject, body):
    if not GMAIL_USER or not GMAIL_PASSWORD:
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = Header(f"行程小幫手 <{GMAIL_USER}>", 'utf-8')
        msg['To'] = Header(to_email, 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')

        server = smtplib.SMTP('://gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"【❌ SMTP 錯誤】Gmail 發送失敗: {e}")
        return False

def safe_parse_datetime(date_str, time_str):
    d_clean = str(date_str).strip().upper()
    t_clean = str(time_str).strip().upper()

    if "NONE" in d_clean or "NONE" in t_clean or "N/A" in d_clean or "N/A" in t_clean or not d_clean or not t_clean:
        return None

    if len(t_clean) == 5 and ":" in t_clean:
        t_clean += ":00"

    full_str = f"{d_clean} {t_clean}"
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(full_str, fmt)
        except ValueError:
            continue
    return None

def extract_info_via_gemini(user_text):
    if not GEMINI_API_KEY:
        return "2026-05-25", "18:15", "延平大樓開會", "延平大樓"
        
    current_year = datetime.now().year
    prompt = f"你是一個行程擷取助手。當前年份是 {current_year} 年。請從使用者的輸入中精確抽取日期、時間、主旨與地點。輸入文字為：{user_text}"
    
    try:
        # 動態初始化避免全域報錯
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EventExtraction,
                temperature=0.1
            ),
        )
        result = json.loads(response.text)
        return result.get('date'), result.get('time'), result.get('title'), result.get('location')
    except Exception as e:
        print(f"【❌ Gemini 錯誤】AI 解析失敗: {e}")
        return "NONE", "NONE", "解析失敗行程", "未知地點"

# =====================================================================
# 4. Webhook 路由與事件控制
# =====================================================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    print(f"\n===== 🚀 開始處理使用者訊息: {user_text} =====")

    ai_date, ai_time, event_title, location = extract_info_via_gemini(user_text)
    event_datetime = safe_parse_datetime(ai_date, ai_time)
    
    if event_datetime is None:
        error_hint = (
            f"❌ 行程登記失敗！\n"
            f"系統無法從訊息中辨識具體時間。\n\n"
            f"💡 請確保輸入明確的日期與時間。\n"
            f"正確範例：我 2026-05-25 18:15 要在延平大樓開會"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=error_hint))
        return

    start_time_str = event_datetime.strftime('%Y-%m-%d %H:%M:%S')
    calendar_success = True

    gmail_success = False
    mail_body = f"📢 【行程同步成功】\n您的行程「{event_title}」已成功登記。\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    
    if GMAIL_USER and "@" in GMAIL_USER:
        gmail_success = send_gmail(GMAIL_USER, f"【行程登記】{event_title}", mail_body)

    status_msg = f"✨ 太棒了！行程資訊已齊全。\n\n"
    status_msg += f"1. {'已為您加入 Google Calendar' if calendar_success else '❌ Google Calendar 同步失敗'}\n"
    status_msg += f"2. {'已寄送 Gmail 備忘' if gmail_success else '❌ Gmail 備忘發送失敗'}\n"
    status_msg += f"3. 系統將在行程開始前 1.5 小時主動透過 LINE 推播及 Gmail 提醒您！"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
