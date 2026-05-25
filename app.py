import os
import json
import datetime
import re
from datetime import timedelta
from flask import Flask, request, abort
from dotenv import load_dotenv

# LINE, Google-GenAI, Google API 套件
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google import genai  
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Gmail 寄信套件
import smtplib
from email.mime.text import MIMEText

# 排程器套件
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = Flask(__name__)

SCOPES = ['https://googleapis.com']

# --- 1. 環境變數與金鑰嚴格檢查 ---
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET") or os.getenv("LINE_CHANNEL_SECRET")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if not LINE_TOKEN or not LINE_SECRET or not GEMINI_KEY:
    print("【系統崩潰】關鍵環境變數（LINE 或 Gemini 金鑰）有缺失，請檢查 Render 後台設定！")
    exit(1)

# 初始化 LINE API
line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# 初始化新版 Gemini Client
try:
    client = genai.Client(api_key=GEMINI_KEY.strip())
    print("【系統通知】新版 Gemini Client 初始化成功！")
except Exception as e:
    print(f"【系統崩潰】Gemini 初始化失敗: {e}")
    exit(1)

# 初始化 APScheduler 排程器
scheduler = BackgroundScheduler()
scheduler.start()

# 用於暫存使用者不完整行程的上下文字典
user_sessions = {}

# --- 2. Google 日曆核心功能 ---
def get_calendar_service():
    """使用服務帳戶金鑰自動取得 Google Calendar 服務"""
    service_account_file = 'service_account.json'
    if os.path.exists(service_account_file):
        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES)
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            print(f"[錯誤] 讀取服務帳戶金鑰失败: {e}")
            return None
    return None

def add_event_to_calendar(summary, location, date_str, time_str, description=""):
    """同步行程至 Google Calendar"""
    service = get_calendar_service()
    if not service:
        print("[警告] Google Calendar 服務不可用，跳過日曆寫入。")
        return None

    start_time_str = f"{date_str}T{time_str}:00"
    start_dt = datetime.datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
    end_dt = start_dt + datetime.timedelta(hours=1) 
    end_time_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    calendar_id = os.getenv("CALENDAR_ID") or 'primary'

    event = {
        'summary': summary,
        'location': location or '',
        'description': description,
        'start': {
            'dateTime': start_time_str,
            'timeZone': 'Asia/Taipei',
        },
        'end': {
            'dateTime': end_time_str,
            'timeZone': 'Asia/Taipei',
        },
    }

    try:
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"[成功] 行程已同步至 Google 行事曆，連結: {event_result.get('htmlLink')}")
        return event_result.get('id')
    except Exception as e:
        print(f"[錯誤] 新增 Google 行事曆行程時發生錯誤: {e}")
        return None

# --- 3. 系統通知中心 ---
def send_gmail(subject, content):
    """透過伺服器後台寄送備忘郵件"""
    sender = os.environ.get("GMAIL_USER") or os.getenv("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    
    if not sender or not password:
        print("【系統錯誤】Gmail 帳號或應用程式密碼未設定。")
        return

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = sender  

    try:
        with smtplib.SMTP_SSL("://gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [sender], msg.as_string())
        print("【系統通知】Gmail 寄送成功")
    except Exception as e:
        print(f"【系統錯誤】Gmail 寄送失敗: {e}")

def reminder_task(user_id, event_title, location, start_time_str):
    """開始前 1.5 小時自動觸發的通知"""
    msg = f"📢 【行程提醒】您的行程「{event_title}」即將在 1.5 小時後開始！\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
    except Exception as e:
        print(f"【系統錯誤】LINE 推播提醒失敗: {e}")
    send_gmail(f"【行程提醒】{event_title}", msg)

def analyze_text_with_gemini(text):
    """利用新版 Gemini 2.5 進行嚴格的 JSON 欄位語意解析 (升級防呆版)"""
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    你是一個行程助理。請分析使用者的輸入，並嚴格以 JSON 格式回應。
    若使用者有提及欄位，請填入數值；若完全沒提及，該欄位請填 null。
    今天的日期是 {current_date}。

    請只輸出符合規範的 JSON 結構，絕對不要包含任何 markdown 標籤（如 ```json）或任何額外解釋文字。

    回應格式範例：
    {{
      "date": "YYYY-MM-DD",
      "time": "HH:MM",
      "location": "地點內容",
      "event": "行程內容"
    }}
    
    使用者輸入：「{text}」
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        # 【核心 Bug 修復點】：利用正規表達式，強制只抓取大括號 {} 內部的 JSON
        raw_text = response.text.strip()
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            clean_text = match.group(0)
            return json.loads(clean_text)
        else:
            return json.loads(raw_text)
    except Exception as e:
        print(f"【系統錯誤】Gemini 解析失敗: {e}")
        return {"date": None, "time": None, "location": None, "event": None}

# --- 4. Webhook 進入點與訊息監聽中心 ---
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
    user_input = event.message.text
    
    extracted_data = analyze_text_with_gemini(user_input)
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {"date": None, "time": None, "location": None, "event": None}
        
    # 合併新舊資訊：如果新解析出來的不是 None，就覆蓋過去
    for key in ["date", "time", "location", "event"]:
        if extracted_data.get(key) is not None and extracted_data[key] != "null" and extracted_data[key] != "":
            user_sessions[user_id][key] = extracted_data[key]
            
    current_session = user_sessions[user_id]
    missing_fields = []
    if not current_session["date"]: missing_fields.append("【日期】")
    if not current_session["time"]: missing_fields.append("【時間】")
    if not current_session["location"]: missing_fields.append("【地點】")
    if not current_session["event"]: missing_fields.append("【要做什麼/事件名稱】")
    
    if missing_fields:
        reply_msg = f"收到部分行程！但您還漏了：{', '.join(missing_fields)}。\n\n目前暫存：\n📅 日期: {current_session['date']}\n⏰ 時間: {current_session['time']}\n📍 地點: {current_session['location']}\n📝 行程: {current_session['event']}\n\n請直接補充告訴我缺漏的資訊！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
    else:
        try:
            # 1. 寫入日曆
            add_event_to_calendar(
                summary=current_session['event'],
                location=current_session['location'],
                date_str=current_session['date'],
                time_str=current_session['time']
            )
            
            # 2. 寄送 Gmail
            success_msg = f"成功記錄行程！\n行程：{current_session['event']}\n時間：{current_session['date']} {current_session['time']}\n地點：{current_session['location']}"
            send_gmail(f"【成功記錄】{current_session['event']}", success_msg)
            
            # 3. 設定 1.5 小時前提醒
            event_datetime_str = f"{current_session['date']} {current_session['time']}"
            event_datetime = datetime.datetime.strptime(event_datetime_str, "%Y-%m-%d %H:%M")
            reminder_time = event_datetime - timedelta(minutes=90)
            
            scheduler.add_job(
                func=reminder_task,
                trigger='date',
                run_date=reminder_time,
                args=[user_id, current_session['event'], current_session['location'], current_session['time']]
            )
            
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"✨ 太棒了！行程資訊已齊全。\n\n1. 已為您加入 Google Calendar (日曆: Ying)\n2. 已寄送 Gmail 備忘\n3. 系統將在行程開始前 1.5 小時（{reminder_time.strftime('%Y-%m-%d %H:%M')}）主動透過 LINE 推播及 Gmail 提醒您！")
            )
            del user_sessions[user_id]
            
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"處理行程時發生錯誤：{str(e)}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
