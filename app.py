import os
import re
from datetime import datetime, timedelta
# 請依據您的專案補上正確的導入，例如：
# from google_calendar_api import add_to_calendar
# from line_bot_api_config import line_bot_api, TextSendMessage

# =====================================================================
# 1. 安全時間解析防禦機制（防止 time data N/A 錯誤）
# =====================================================================
def safe_parse_datetime(date_str, time_str):
    """安全地將 AI 抽取出的日期與時間字串轉換為 datetime 物件"""
    date_str = str(date_str).strip().upper() if date_str else ""
    time_str = str(time_str).strip().upper() if time_str else ""

    # 防呆：如果 AI 丟出 N/A, None 或空白，直接判定失敗，不進行字串拼接
    if not date_str or not time_str or "N/A" in date_str or "N/A" in time_str or "NONE" in date_str or "NONE" in time_str:
        print(f"【⚠️ 欄位缺失】AI 解析出無效時間資料 - 日期: '{date_str}', 時間: '{time_str}'")
        return None

    # 如果時間只有 HH:MM，自動補上秒數 :00
    if len(time_str) == 5 and ":" in time_str:
        time_str += ":00"

    full_str = f"{date_str} {time_str}"

    # 嘗試多種常見格式解析
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(full_str, fmt)
        except ValueError:
            continue

    print(f"【❌ 格式不符】無法識別的時間格式組合: {full_str}")
    return None


# =====================================================================
# 2. LINE Webhook 核心主流程（處理使用者傳來的每句話）
# =====================================================================
def handle_line_user_message(user_id, user_text):
    """
    當使用者傳送：「我 2026-05-25 18:15 要在延平大樓開會」時觸發此函數
    """
    print(f"\n===== 🚀 開始處理使用者訊息: {user_text} =====")

    # -----------------------------------------------------------------
    # 步驟 1：呼叫您的 AI (如 OpenAI) 或 Regex 抽取資訊
    # -----------------------------------------------------------------
    # 💡 請在此處替換成您實際呼叫 GPT / LLM 的代碼
    # 這裡我們模擬 AI 正常運作抓取到的資料：
    ai_extracted_date = "2026-05-25"  
    ai_extracted_time = "18:15"       
    event_title = "延平大樓開會"
    location = "延平大樓"
    
    # -----------------------------------------------------------------
    # 步驟 2：時間防禦驗證
    # -----------------------------------------------------------------
    event_datetime = safe_parse_datetime(ai_extracted_date, ai_extracted_time)
    
    if event_datetime is None:
        # 如果時間解析失敗，立刻擋下並在 LINE 提示使用者，後續流程全部不執行
        error_hint = (
            f"❌ 行程設定失敗！\n"
            f"系統無法辨識時間。請確保訊息包含明確的日期與時間。\n"
            f"範例：開會 2026-05-25 18:15"
        )
        line_bot_api.push_message(user_id, TextSendMessage(text=error_hint))
        return False

    # 轉換成標準格式字串，供後續 API 使用
    start_time_str = event_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # -----------------------------------------------------------------
    # 步驟 3：寫入 Google Calendar（獨立 try...except 隔離）
    # -----------------------------------------------------------------
    calendar_success = False
    try:
        print("正在寫入 Google Calendar...")
        # 💡 請替換成您實際寫入 Google 日曆的函數
        # add_to_calendar(title=event_title, start_time=start_time_str, location=location)
        calendar_success = True
        print("✅ Google Calendar 寫入成功！")
    except Exception as e:
        print(f"【❌ 系統錯誤】寫入 Google Calendar 失敗: {e}")

    # -----------------------------------------------------------------
    # 步驟 4：發送 Gmail 備忘信件（獨立 try...except 隔離）
    # -----------------------------------------------------------------
    gmail_success = False
    mail_body = f"📢 【行程備忘】您的行程「{event_title}」已登記。\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    try:
        print("正在發送 Gmail 備忘信...")
        send_gmail(f"【行程登記成功】{event_title}", mail_body)
        gmail_success = True
        print("✅ Gmail 登記備忘發送成功！")
    except Exception as e:
        print(f"【❌ 系統錯誤】當下發送 Gmail 備忘失敗: {e}")

    # -----------------------------------------------------------------
    # 步驟 5：啟動 1.5 小時前的排程提醒任務（如 Celery / APScheduler）
    # -----------------------------------------------------------------
    try:
        print("正在建立 1.5 小時前非同步提醒排程...")
        # 計算觸發時間 = 行程時間 - 1.5 小時
        trigger_time = event_datetime - timedelta(hours=1.5)
        
        # 💡 請在此處呼叫您的排程器，例如 Celery:
        # reminder_task.apply_async(args=[user_id, event_title, location, start_time_str], eta=trigger_time)
        print(f"✅ 非同步排程設定成功！將於 {trigger_time.strftime('%Y-%m-%d %H:%M:%S')} 觸發提醒。")
    except Exception as e:
        print(f"【❌ 系統錯誤】設定 Celery 非同步排程失敗: {e}")

    # -----------------------------------------------------------------
    # 步驟 6：回覆使用者最終狀態（根據前面各步驟的成功與否動態組合訊息）
    # -----------------------------------------------------------------
    status_msg = f"✨ 太棒了！行程資訊已齊全。\n\n"
    status_msg += f"1. {'已為您加入 Google Calendar' if calendar_success else '❌ Google Calendar 同步失敗'}\n"
    status_msg += f"2. {'已寄送 Gmail 備忘' if gmail_success else '❌ Gmail 備忘發送失敗'}\n"
    status_msg += f"3. 系統將在行程開始前 1.5 小時主動透過 LINE 推播及 Gmail 提醒您！"

    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=status_msg))
    except Exception as e:
        print(f"【❌ 系統錯誤】發送 LINE 狀態回覆失敗: {e}")

    return True


# =====================================================================
# 3. 背景排程提醒任務（1.5 小時前由排程器觸發）
# =====================================================================
def reminder_task(user_id, event_title, location, start_time_str):
    """此函數僅在行程前 1.5 小時被非同步觸發，負責最後的雙管道推播"""
    print(f"== ⏰ 觸發 1.5 小時前提醒任務: {event_title} ==")
    msg = f"📢 【行程提醒】您的行程「{event_title}」即將在 1.5 小時後開始！\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    
    # LINE 推播
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
    except Exception as e:
        print(f"【❌ 系統錯誤】排程提醒 - LINE 推播失敗: {e}")
        
    # Gmail 推播
    try:
        send_gmail(f"【行程提醒】{event_title}", msg)
    except Exception as e:
        print(f"【❌ 系統錯誤】排程提醒 - Gmail 發送失敗: {e}")
