import os
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 載入 .env 檔案（如果本地測試有這個檔案的話）
load_dotenv()

# 2. 【核心修正】先嘗試讀取 Render 的系統環境變數，如果沒有，再找本地變數
api_key = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

# 3. 強制進行嚴格檢查與錯誤回報
if not api_key:
    # 輸出這行會讓你在 Render 的 Logs 黑色畫面看到到底發生什麼事
    print("【系統錯誤】OS 環境變數中完全找不到 GEMINI_API_KEY，請確認 Render 後台是否有按 Save Changes。")
else:
    # 去除前後可能不小心複製到的空白字元
    api_key = api_key.strip()
    print(f"【系統通知】成功偵測到金鑰，開頭為: {api_key[:5]}...")
    
    # 4. 根據你使用的新舊版套件，使用最安全的初始化語法
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"【系統錯誤】Gemini 初始化失敗: {e}")
