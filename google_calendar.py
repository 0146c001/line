# 🟢 欄位皆完整，執行記錄流程
try:
    # 1. 呼叫你剛寫好的日曆管理函式
    add_event_to_calendar(
        summary=current_session['event'],
        location=current_session['location'],
        date_str=current_session['date'],
        time_str=current_session['time']
    )
    
    # 2. 寄送 1.5 小時前的定時通知 (APScheduler)
    event_datetime_str = f"{current_session['date']} {current_session['time']}"
    event_datetime = datetime.strptime(event_datetime_str, "%Y-%m-%d %H:%M")
    reminder_time = event_datetime - timedelta(minutes=90)
    
    scheduler.add_job(
        func=reminder_task,
        trigger='date',
        run_date=reminder_time,
        args=[user_id, current_session['event'], current_session['location'], current_session['time']]
    )
    
    # 3. 回覆 LINE 訊息
    line_bot_api.reply_message(
        event.reply_token, 
        TextSendMessage(text=f"✨ 成功同步至您的日曆（Ying）！\n系統將在行程開始前 1.5 小時透過 LINE 及 Gmail 提醒您。")
    )
    del user_sessions[user_id] # 清除該次記憶

except Exception as e:
    print(f"寫入失敗: {e}")
