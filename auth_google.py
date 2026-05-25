import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    if not os.path.exists('credentials.json'):
        print("="*60)
        print("錯誤：找不到 credentials.json 檔案！")
        print("請依以下步驟設定並取得憑證：")
        print("1. 前往 Google Cloud Console (https://console.cloud.google.com/)。")
        print("2. 建立新專案或選擇現有專案。")
        print("3. 啟用「Google Calendar API」。")
        print("4. 前往「憑證 (Credentials)」頁面，點選「建立憑證」→「OAuth 用戶端 ID」。")
        print("5. 應用程式類型選擇「桌面版應用程式 (Desktop App)」，並建立。")
        print("6. 下載 JSON 格式的用戶端金鑰，將檔案重新命名為 `credentials.json` 並放置於此目錄。")
        print("="*60)
        return

    try:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        
        print("="*60)
        print("成功！已生成 token.json 憑證檔案。")
        print("現在您的 Line 機器人已可存取您的 Google 行事曆。")
        print("="*60)
    except Exception as e:
        print(f"授權失敗或發生錯誤: {e}")

if __name__ == '__main__':
    main()
