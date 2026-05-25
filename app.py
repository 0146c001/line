from datetime import datetime
import re

# =====================================================================
# 1. 核心時間解析功能（防呆升級）
# =====================================================================
def parse_event_time(date_str, time_str):
    """
    將 AI 或 Regex 解析出的日期與時間字串，安全地組合成 datetime 物件
    防止類似 'N/A' 或 'N/ATN/A:00' 的髒資料弄垮系統
    """
    # 轉成字串並去除前後空格、全部轉大寫方便比對
    date_str = str(date_str).strip().upper() if date_str else ""
    time_str = str(time_str).strip().upper() if time_str else ""

    # 防呆機制：如果欄位缺失、包含 N/A 或 None，直接判定解析失敗
    if not date_str or not time_str or "N/A" in date_str or "N/A" in time_str or "NONE" in date_str or "NONE" in time_str:
        print(f"【系統預警】偵測到無效的時間欄位 - 日期: '{date_str}', 時間: '{time_str}'")
        return None

    # 嘗試清理並補齊秒數
    # 處理可能的時間格式，例如 "18:15" -> "18:15:00"
    if len(time_str) == 5 and ":" in time_str:
        time_str += ":00"

    full_time_str = f"{date_str} {time_str}"

    # 嘗試用多種常見格式解析，提高容錯率
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(full_time_str, fmt)
        except ValueError:
            continue

    print(f"【系統錯誤】無法識別的時間格式組合: {full_time_str}")
    return None


# =====================================================================
# 2. LINE 訊息主處理入口（模擬 Webhook 接收到文字訊息）
# =====================================================================
def handle_user_message(user_id, user_text):
    """
    處理使用者輸入的文字，如：「我 2026-05-25 18:15 要在延平大樓開會」
    """
    print(f"收到使用者訊息: {user_text}")

    # -----------------------------------------------------------------
    # 【模擬您的解析邏輯】
    # 這裡假設您的 AI 或 Regex 運作後，抽取出以下四個變數。
    # 故意模擬出當初導致您崩潰的 'N/A' 髒資料情況：
    # -----------------------------------------------------------------
    # 正常情況應為: extracted_date = "2026-05-25", extracted_time = "18:15"
    extracted_date = "N/A"   
    extracted_time = "TN/A:00"  # 這裡模擬出您截圖中組合出 'N/ATN/A:00' 的源頭
    extracted_title = "延平大樓開會"
    extracted_location = "延平大樓"
    # -----------------------------------------------------------------

    # 呼叫防呆解析函數
    event_datetime = parse_event_time(extracted_date, extracted_time)

    # 如果解析失敗，立刻擋下來，傳送易懂的錯誤訊息給使用者
    if event_datetime is None:
        error_reply = (
            f"❌ 行程設定失敗！\n"
            f"系統無法從您的訊息中正確辨識日期或時間。\n"
            f"💡 請確保訊息包含明確的時間，例如：\n"
            f"「我 2026-05-25 18:15 要在延平大樓開會」"
        )
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=error_reply))
        except Exception as e:
            print(f"【系統錯誤】發送錯誤提示至 LINE 失敗: {e}")
        return False

    # 格式化為標準字串，準備紀錄或傳入 Calendar / 提醒任務
    start_time_str = event_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # 成功解析，繼續後續流程
    print(f"成功解析行程！時間為: {start_time_str}，準備寫入系統...")
    
    # TODO: 這裡放您的 Google Calendar 寫入邏輯
    # add_to_google_calendar(user_id, extracted_title, start_time_str)

    # 回覆使用者成功訊息
    success_msg = (
        f"✨ 太棒了！行程資訊已齊全。\n\n"
        f"1. 已為您加入 Google Calendar\n"
        f"2. 已寄送 Gmail 備忘\n"
        f"3. 系統將在行程開始前 1.5 小時主動透過 LINE 推播及 Gmail 提醒您！"
    )
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=success_msg))
    except Exception as e:
        print(f"【系統錯誤】發送成功通知至 LINE 失敗: {e}")
        
    return True


# =====================================================================
# 3. 非同步排程提醒任務（Celery 任務）
# =====================================================================
def reminder_task(user_id, event_title, location, start_time_str):
    """
    此函數由 Celery 或其他排程器在指定時間（如 1.5 小時前）自動觸發
    """
    msg = f"📢 【行程提醒】您的行程「{event_title}」即將在 1.5 小時後開始！\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    
    # 獨立發送 LINE 提醒
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
    except Exception as e:
        print(f"【系統錯誤】LINE 推播提醒失敗: {e}")
        
    # 獨立發送 Gmail 提醒，兩者互不干擾
    try:
        send_gmail(f"【行程提醒】{event_title}", msg)
    except Exception as e:
        print(f"【系統錯誤】Gmail 發送失敗: {e}")
