import os
import json
import datetime
from datetime import timedelta
from flask import Flask, request, abort
from dotenv import load_dotenv

# LINE, Google-GenAI, Google API 套件
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google import genai  
from google.genai import types  # <-- 引入結構化型態套件
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

line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

try:
    client = genai.Client(api_key=GEMINI_KEY.strip())
    print("【系統通知】新版 Gemini Client 初始化成功！")
except Exception as e:
    print(f"【系統崩潰】Gemini 初始化失敗: {e}")
    exit(1)

scheduler = BackgroundScheduler()
scheduler.start()

user_sessions = {}

# --- 2. Google 日曆核心功能 ---
def get_calendar_service():
    service_account_file = 'service_account.json'
    if os.path.exists(service_account_file):
        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES)
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            print(f"[錯誤] 讀取服務帳戶金鑰失敗: {e}")
    return None

def add_event_to_calendar(summary, location, date_str, time_str, description=""):
    service = get_calendar_service()
    if not service:
        print("[警告] Google Calendar 服務不可用。")
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
        'start': {'dateTime': start_time_str, 'timeZone': 'Asia/Taipei'},
        'end': {'dateTime': end_time_str, 'timeZone': 'Asia/Taipei'},
    }

    try:
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        return event_result.get('id')
    except Exception as e:
        print(f"[錯誤] 新增 Google 行事曆行程失敗: {e}")
        return None

# --- 3. 系統通知中心 ---
def send_gmail(subject, content):
    sender = os.environ.get("GMAIL_USER") or os.getenv("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    
    if not sender or not password:
        return

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = sender  

    try:
        with smtplib.SMTP_SSL("://gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [sender], msg.as_string())
    except Exception as e:
        print(f"【系統錯誤】Gmail 寄送失敗: {e}")

def reminder_task(user_id, event_title, location, start_time_str):
    msg = f"📢 【行程提醒】您的行程「{event_title}」即將在 1.5 小時後開始！\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
    except Exception as e:
        print(f"【系統錯誤】LINE 推播提醒失敗: {e}")
    send_gmail(f"【行程提醒】{event_title}", msg)

def analyze_text_with_gemini(text):
    """【史詩級升級】使用 Google 官方指定 Schema 結構化強制輸出 JSON"""
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"分析以下使用者的輸入並擷取行程資訊。今天日期是 {current_date}。輸入內容：{text}"
    
    # 強制規定 Gemini 必須吐出的欄位結構與型態
    response_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "date": types.Schema(type=types.Type.STRING, description="格式為 YYYY-MM-DD，若未提及填空字串"),
            "time": types.Schema(type=types.Type.STRING, description="格式為 HH:MM，若未提及填空字串"),
            "location": types.Schema(type=types.Type.STRING, description="地點，若未提及填空字串"),
            "event": types.Schema(type=types.Type.STRING, description="行程要做什麼，若未提及填空字串"),
        },
        required=["date", "time", "location", "event"]
    )
    
    try:
        # 強制指定輸出為 json 物件
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.1
            ),
        )
        
        # 直接讀取，絕對不會有 Markdown 標籤汙染
        data = json.loads(response.text.strip())
        
        # 標準化空值轉換
        for k in ["date", "time", "location", "event"]:
            if not data.get(k) or data[k] == "null" or data[k] == "None":
                data[k] = None
        return data
    except Exception as e:
        print(f"【關鍵錯誤】Gemini 結構化解析失敗: {e}")
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
        
    for key in ["date", "time", "location", "event"]:
        if extracted_data.get(key) is not None:
            user_sessions[user_id][key] = extracted_data[key]
            
    current_session = user_sessions[user_id]
    missing_fields = []
    if not current_session["date"]: missing_fields.append("【日期】")
    if not current_session["time"]: missing_fields.append("【時間】")
    if not current_session["location"]: missing_fields.append("【地點】")
    if not current_session["event"]: missing_fields.append("【要做什麼/事件名稱】")
    
    if missing_fields:
        reply_msg = f"收到部分行程！但您還漏了：{', '.join(missing_fields)}。\n\n目前暫存：\n📅 日期: {current_session['date'] or '尚未取得'}\n⏰ 時間: {current_session['time'] or '尚未取得'}\n📍 地點: {current_session['location'] or '尚未取得'}\n📝 行程: {current_session['event'] or '尚未取得'}\n\n請直接補充告訴我缺漏的資訊！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
    else:
        try:
            add_event_to_calendar(
                summary=current_session['event'],
                location=current_session['location'],
                date_str=current_session['date'],
                time_str=current_session['time']
            )
            
            success_msg = f"成功記錄行程！\n行程：{current_session['event']}\n時間：{current_session['date']} {current_session['time']}\n地點：{current_session['location']}"
            send_gmail(f"【成功記錄】{current_session['event']}", success_msg)
            
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
