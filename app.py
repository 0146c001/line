from datetime import datetime
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage

# 註：使用前請確保 configuration 已正確設定
# configuration = Configuration(access_token='YOUR_CHANNEL_ACCESS_TOKEN')

def parse_start_time(start_time_str):
    """安全解析時間字串，防止格式錯誤導致系統崩潰"""
    if not start_time_str or "N/A" in str(start_time_str).upper():
        print(f"【系統預警】收到無效的時間字串: {start_time_str}")
        return None
    try:
        return datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError as e:
        print(f"【系統預警】時間格式不符 (%Y-%m-%d %H:%M:%S): {e}")
        return None


def reminder_task(user_id, event_title, location, start_time_str):
    """排程提醒核心任務（LINE SDK v3 版本）"""
    
    # 1. 優先驗證時間資料
    start_time = parse_start_time(start_time_str)
    
    if start_time is None:
        error_msg = f"❌ 行程「{event_title}」處理失敗。\n原因：系統無法解析時間資料（您的輸入：{start_time_str}），請重新檢查設定。"
        try:
            with ApiClient(configuration) as api_client:
                api = MessagingApi(api_client)
                api.push_message(PushMessageRequest(to=user_id, messages=[TextMessage(text=error_msg)]))
        except Exception as e:
            print(f"【系統錯誤】發送錯誤回報至 LINE 失敗: {e}")
        return False

    # 2. 時間驗證通過，組合正式提醒訊息
    msg = f"📢 【行程提醒】您的行程「{event_title}」即將在 1.5 小時後開始！\n📍 地點：{location}\n⏰ 時間：{start_time_str}"
    
    # 3. LINE v3 推播
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_request = PushMessageRequest(to=user_id, messages=[TextMessage(text=msg)])
            line_bot_api.push_message(push_request)
    except Exception as e:
        print(f"【系統錯誤】LINE 推播提醒失敗: {e}")
        
    # 4. Gmail 發送
    try:
        send_gmail(f"【行程提醒】{event_title}", msg)
    except Exception as e:
        print(f"【系統錯誤】Gmail 發送失敗: {e}")
        
    return True
