import os
import re
from datetime import datetime, timedelta
from flask import Flask, request, abort

# 💡 請確保您的 requirements.txt 裡面有加上 line-bot-sdk 與 flask
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# =====================================================================
# 1. 初始化 Flask 與 LINE Bot (讓 Render 找不到 'app' 的問題根治)
# =====================================================================
app = Flask(__name__)

# 請在 Render 的 Environment 填入這兩個環境變數，或直接填入字串
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '您的CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '您的CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 模擬您的 Gmail 發送函式 (請替換成您原本的 Gmail 實作)
def send_gmail(subject, body):
    print(f"【發送 Gmail】主旨: {subject}")
    # 您的 Gmail 寄信邏輯放這裡
    pass

# =====================================================================
# 2. 安全時間解析防禦機制（防止 time data N/A 錯誤）
# =====================================================================
def safe_parse_datetime(date_str, time_str):
    date_str = str(date_str).strip().upper() if date_str else ""
    time_str = str(time_str).strip().upper() if time_str else ""

    if not date_str or not time_str or "N/A" in date_str or "N/A" in time_str or "NONE" in date_str or "NONE" in time_str:
        print(f"【⚠️ 欄位缺失】AI 解析出無效時間資料 - 日期: '{date_str}', 時間: '{time_str}'")
        return None

    if len(time_str) == 5 and ":" in time_str:
        time_str += ":00"

    full_str = f"{date_str} {time_str}"

    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(full_str, fmt)
        except ValueError:
            continue

    print(f"【❌ 格式不符】無法識別的時間格式組合: {full_str}")
    return None

# =====================================================================
# 3. LINE Webhook 路由與事件處理
# =====================================================================
@app.route("/callback", methods=['POST'])
def callback():
    """接收 LINE 伺服器傳來的 Webhook 訊號"""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """當使用者傳送文字訊息時觸發"""
    user_id = event.source.user_id
    user_text = event.message.text
    
    print(f"\n===== 🚀 開始處理使用者訊息: {user_text} =====")

    # -----------------------------------------------------------------
    # 💡 步驟 1：呼叫您的 AI (如 OpenAI) 抽取資訊
    # 這裡先靜態模擬成功與失敗的狀況，請置換成您的 AI 抽取邏輯
    # -----------------------------------------------------------------
    ai_extracted_date = "2026-05-25"  
    ai_extracted_time = "18:15"       
    event_title = "延平大樓開會"
    location = "延平大樓"
    
    # -----------------------------------------------------------------
    # 步驟 2：時間防禦驗證
    # -----------------------------------------------------------------
    event_datetime = safe_parse_datetime(ai_extracted_date, ai_extracted_time)
    
    if event_datetime is None:
        error_hint = (
            f"❌ 行程設定失敗！\n"
            f"系統無法辨識時間。請確保訊息包含明確的日期與時間。\n"
            f"範例：開會 2026-05-25 18:15"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=error_hint))
        return

    start_time_str = event_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # -----------------------------------------------------------------
    # 步驟 3：寫入 Google Calendar
    # -----------------------------------------------------------------
    calendar_success = False
    try:
        # 💡 請在此處補上您實際寫入 Google 日曆的函數
        # add_to_calendar(title=event_title, start_time=start_time_str, location=location)
        calendar_success = True
    except Exception as e:
        print(f"【❌ 系統錯誤】寫入 Google Calendar 失敗: {e}")

    # -----------------------------------------------------------------
    # 步驟 4：發送 Gmail 備忘信件
    # -----------------------------------------------------------------
    gmail_success = False
    mail_body = f"📢 【行程備忘】您的行程「{event_title}」已登記。\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    try:
        send_gmail(f"【行程登記成功】{event_title}", mail_body)
        gmail_success = True
    except Exception as e:
        print(f"【❌ 系統錯誤】當下發送 Gmail 備忘失敗: {e}")

    # -----------------------------------------------------------------
    # 步驟 5：動態組合訊息並回覆給手機端
    # -----------------------------------------------------------------
    status_msg = f"✨ 太棒了！行程資訊已齊全。\n\n"
    status_msg += f"1. {'已為您加入 Google Calendar' if calendar_success else '❌ Google Calendar 同步失敗'}\n"
    status_msg += f"2. {'已寄送 Gmail 備忘' if gmail_success else '❌ Gmail 備忘發送失敗'}\n"
    status_msg += f"3. 系統將在行程開始前 1.5 小時主動透過 LINE 推播及 Gmail 提醒您！"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
