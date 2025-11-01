import os
import requests

def send_email(recipient: str, subject: str, html_content: str):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "Project Aurion", "email": "noreply@yourdomain.com"},
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html_content
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        print(f"[EmailSend] success -> {recipient}")
        return True
    else:
        print(f"[EmailSend] failed -> {recipient} | {response.text}")
        return False
