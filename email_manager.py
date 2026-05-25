import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def send_gmail(subject, body):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    receiver_email = os.getenv("RECEIVER_EMAIL") or sender_email

    if not sender_email or not sender_password:
        print("[警告] 郵件設定不足，未設定 SENDER_EMAIL 或 SENDER_PASSWORD！無法寄送 Gmail。")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject

    # Support UTF-8 encoding
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print(f"[成功] 郵件寄送完成：{subject} 發送給 {receiver_email}")
        return True
    except Exception as e:
        print(f"[錯誤] 發送郵件時發生錯誤: {e}")
        return False
