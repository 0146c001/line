from google import genai
from google.genai import types
import os
import datetime
from zoneinfo import ZoneInfo
import json
from dotenv import load_dotenv

load_dotenv()

def parse_event_message(user_message, current_session=None):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[警告] 未設定 GEMINI_API_KEY，無法呼叫 Gemini API！")
        return {
            "date": None,
            "time": None,
            "location": None,
            "description": None,
            "missing_fields": ["date", "time", "location", "description"],
            "is_event_creation": False,
            "reply_text": "機器人目前缺少 Gemini API 金鑰設定，請先設定您的金鑰。"
        }

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[錯誤] 初始化 Gemini Client 失敗: {e}")
        return None

    # Get current time in Asia/Taipei timezone
    taipei_tz = ZoneInfo("Asia/Taipei")
    now_taipei = datetime.datetime.now(taipei_tz)
    
    # Map weekday number to friendly Chinese characters
    weekdays = ["日", "一", "二", "三", "四", "五", "六"]
    weekday_str = weekdays[int(now_taipei.strftime("%w"))]
    current_time_friendly = now_taipei.strftime(f"%Y-%m-%d %H:%M:%S (星期{weekday_str})")

    # If there is a pending session, pass its contents to Gemini so it can combine
    previous_data = "{}"
    if current_session and current_session.get('pending_event'):
        previous_data = json.dumps(current_session['pending_event'], ensure_ascii=False)

    prompt = f"""
你是一個智慧行事曆助手。你的任務是從使用者的對話中提取或補充行事曆行程資訊。
目前的系統時間是：{current_time_friendly}。

使用者先前的行程暫存資料（若為空代表新行程）：
{previous_data}

使用者的最新訊息：
「{user_message}」

請分析最新訊息並結合暫存資料，提取出以下四個行程核心欄位：
1. date: 行程日期，格式必須為 YYYY-MM-DD。如果使用者說「明天」、「後天」、「下週三」等，請以目前系統時間為基準，計算出正確的西元日期。如果尚未提供或不明確，請填 null。
2. time: 行程時間，格式必須為 24小時制的 HH:MM。如果使用者說「下午三點」請填 "15:00"，「早上九點半」請填 "09:30"。如果尚未提供或不明確，請填 null。
3. location: 行程地點。如果尚未提供，請填 null。
4. description: 行程內容（要做什麼，例如：野餐、開會、看牙醫）。如果尚未提供，請填 null。

特殊指令：
- 如果使用者表達「取消」、「不用了」、「沒事了」、「不用記了」等想要放棄或取消目前記錄行程的意思，請將 date, time, location, description 全部填為 null，且 missing_fields 填為 []（空陣列），並將 is_event_creation 設為 true，並且 reply_text 填寫類似「好的，已為您取消本次的行程記錄。」的回覆。

行程判斷與回覆規則：
- 只要使用者是在試圖「新增行程」或「補充行程資訊（如回答時間、地點等）」，is_event_creation 就應為 true。如果使用者只是隨意問候（如：你好、謝謝、你是誰）或問非行程問題，is_event_creation 請填 false。
- 請檢查 date, time, location, description 這四個欄位。如果 is_event_creation 為 true 且非取消指令，任何一個欄位為 null 時，請將該欄位的英文名稱放入 missing_fields 陣列中（例如 ["time", "location"]）。
- reply_text 的設計：
  - 如果 is_event_creation 為 false，請填寫對該日常對話的簡短親切回覆。
  - 如果 is_event_creation 為 true 且有缺失欄位，請設計一段親切的中文回覆，告訴使用者目前已記錄什麼（例如：『好的，已收到您的行程「看醫生」』），並明確詢問缺少的欄位（例如：『請問這項行程的「日期」、「時間」及「地點」分別是什麼呢？』）。
  - 如果 is_event_creation 為 true 且無缺失欄位（非取消），請填寫確認已收到完整行程的訊息（例如：『好的，已收到您的完整行程！我會立刻為您記錄、寄送 Gmail 並同步到 Google 行事曆。』）。

請嚴格返回以下 JSON 格式，直接返回 JSON 字串，不要包含任何 markdown 語法如 ```json：
{{
  "date": "YYYY-MM-DD 或 null",
  "time": "HH:MM 或 null",
  "location": "字串 或 null",
  "description": "字串 或 null",
  "missing_fields": ["date", "time", "location", "description" 等欄位中的缺失項],
  "is_event_creation": true/false,
  "reply_text": "給使用者的回覆訊息字串"
}}
"""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        # Parse the JSON output safely
        text_content = response.text.strip()
        # Clean potential markdown wrappers just in case
        if text_content.startswith("```"):
            lines = text_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text_content = "\n".join(lines).strip()
            
        result = json.loads(text_content)
        return result
    except Exception as e:
        print(f"[錯誤] Gemini API 呼叫或解析 JSON 失敗: {e}")
        return None
