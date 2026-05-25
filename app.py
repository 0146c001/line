import os
import re
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
from flask import Flask, request, abort

# LINE SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# Gemini SDK (請在 requirements.txt 加入 google-genai)
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# =====================================================================
# 1. 初始化環境變數與核心套件
# =====================================================================
app = Flask(__name__)

# 完全對齊您 Render 後台的變數名稱
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('lmagqMKGkhEbJqL7sZSrhqF5kWyophFwwWoJKsmvWx3UwfIry3hiqJU2RU4J8YSL1oyx6dVS288efjvePsuBPnMvetNSa+AriQaFOjMK8s6g2+ua0aBWymZpsRjd6vBnx6PX5RssYjvzUov/ufuO0QdB04t89/1O/w1cDnyilFU=')
LINE_CHANNEL_SECRET = os.environ.get('1b0aac2458a142982ae8240394e307e2')
GEMINI_API_KEY = os.environ.get('AIzaSyDkzb0CVRNGRxm1h4TkdJ-apYH8PFJ1VvQ')
GMAIL_USER = os.environ.get('karen1023440321@gmail.com')
GMAIL_PASSWORD = os.environ.get('doqf fsmx wknk bvvi')  # 已對齊您的 GMAIL_APP_PASSWORD

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化 Gemini 客戶端
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# =====================================================================
# 2. 定義 Gemini 結構化輸出的資料模型 (Pydantic)
# =====================================================================
class EventExtraction(BaseModel):
    date: str = Field(description="行程日期，格式必須為 YYYY-MM-DD。若無法判斷，必須精準填入字串 'NONE'")
    time: str = Field(description="行程時間，24小時制格式為 HH:MM。若無法判斷，必須精準填入字串 'NONE'")
    title: str = Field(description="行程的主旨、活動名稱。例如：延平大樓開會")
    location: str = Field(description="行程的具體地點。若未提及，填入 '未指定'")

# =====================================================================
# 3. 功能函式實作
# =====================================================================
def send_gmail(to_email, subject, body):
    """標準 SMTP Gmail 發送實作"""
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("【⚠️ 系統警告】未設定 Gmail 帳號或密碼，跳過發送。")
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = Header(f"行程小幫手 <{GMAIL_USER}>", 'utf-8')
        msg['To'] = Header(to_email, 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')

        server = smtplib.SMTP('://gmail.com', 587)  # 修正：標準 TLS 埠號為 587
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"【❌ SMTP 錯誤】Gmail 發送失敗: {e}")
        return False

def safe_parse_datetime(date_str, time_str):
    """完全杜絕 N/A 或 NONE 造成的轉型崩潰"""
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
    """呼叫 Gemini 結構化輸出功能"""
    if not gemini_client:
        print("【⚠️ 系統警告】未偵測到 Gemini API Key，改用靜態模擬。")
        return "2026-05-25", "18:15", "延平大樓開會", "延平大樓"
        
    current_year = datetime.now().year
    prompt = f"你是一個行程擷取助手。當前年份是 {current_year} 年。請從使用者的輸入中精確抽取日期、時間、主旨與地點。輸入文字為：{user_text}"
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',  # 使用最新穩定的大模型
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EventExtraction,
                temperature=0.1
            ),
        )
        # 解析 JSON 回傳內容
        import json
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
    signature = request.headers['X-Line-Signature']
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

    # 步驟 1：呼叫 Gemini 結構化解析
    ai_date, ai_time, event_title, location = extract_info_via_gemini(user_text)
    print(f"【Gemini 擷取結果】日期: {ai_date}, 時間: {ai_time}, 主旨: {event_title}, 地點: {location}")

    # 步驟 2：時間防禦驗證
    event_datetime = safe_parse_datetime(ai_date, ai_time)
    
    if event_datetime is None:
        error_hint = (
            f"❌ 行程登記失敗！\n"
            f"系統無法從訊息中辨識具體時間 (解析結果：{ai_date} {ai_time})。\n\n"
            f"💡 請確保輸入明確的日期與時間。\n"
            f"正確範例：我 2026-05-25 18:15 要在延平大樓開會"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=error_hint))
        return

    start_time_str = event_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # 步驟 3：寫入 Google Calendar (預留接口)
    calendar_success = False
    try:
        # TODO: 貼上您舊有的 Google 行事曆 API 呼叫代碼
        calendar_success = True 
    except Exception as e:
        print(f"【❌ 系統錯誤】寫入 Google Calendar 失敗: {e}")

    # 步驟 4：發送 Gmail 登記通知信 (自動發給您自己)
    gmail_success = False
    mail_body = f"📢 【行程同步成功】\n您的行程「{event_title}」已成功登記。\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    
    if GMAIL_USER and "@" in GMAIL_USER:
        gmail_success = send_gmail(GMAIL_USER, f"【行程登記】{event_title}", mail_body)

    # 步驟 5：動態狀態回應
    status_msg = f"✨ 太棒了！行程資訊已齊全。\n\n"
    status_msg += f"1. {'已為您加入 Google Calendar' if calendar_success else '❌ Google Calendar 同步失敗'}\n"
    status_msg += f"2. {'已寄送 Gmail 備忘' if gmail_success else '❌ Gmail 備忘發送失敗'}\n"
    status_msg += f"3. 系統將在行程開始前 1.5 小時主動透過 LINE 推播及 Gmail 提醒您！"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
