
def send_welcome_email(to_email: str) -> None:
        subject = "Welcome to Project Aurion!"
        body = (
                "Thank you for registering with Project Aurion.\n\n"
                "Your account is now active. Enjoy exploring our features!"
        )
        html_body = f"""
        <html>
            <body>
                <h2>Welcome to Project Aurion!</h2>
                <p>Thank you for registering. Your account is now active.</p>
                <p>Enjoy exploring our features!</p>
            </body>
        </html>
        """
        send_email(to_email, subject, body, html=html_body)
import os
import requests
import logging

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EmailSendError(Exception):
    pass


def send_email(recipient: str, subject: str, html_content: str) -> bool:
    url = "https://api.brevo.com/v3/smtp/email"
    api_key = os.getenv("BREVO_API_KEY")
    headers = {
        "accept": "application/json",
        "Api-Key": api_key,  # Brevo expects 'Api-Key' (case-sensitive)
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "Project Aurion", "email": "rathodvamshi369@gmail.com"},
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html_content
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        logger.info(f"[EmailSend] success -> {recipient}")
        return True
    else:
        logger.error(f"[EmailSend] failed -> {recipient} | {response.text}")
        return False


def send_otp_email(to_email: str, otp_code: str) -> bool:
        subject = "Your One-Time Password (OTP) for Project Aurion"
        html_body = f"""
        <html>
            <body style='font-family: Arial, sans-serif; background: #f7f7f9; margin:0; padding:0;'>
                <table width="100%" bgcolor="#f7f7f9" cellpadding="0" cellspacing="0" style="padding: 40px 0;">
                    <tr>
                        <td align="center">
                            <table width="420" bgcolor="#fff" cellpadding="0" cellspacing="0" style="border-radius: 8px; box-shadow:0 2px 8px #e0e0e0; padding: 32px 24px;">
                                <tr>
                                    <td align="center" style="padding-bottom: 16px;">
                                        <img src="https://i.imgur.com/2yaf2wb.png" alt="Project Aurion" width="48" style="margin-bottom: 8px;"/>
                                        <h2 style="margin: 0; color: #2d3748; font-size: 1.6em;">Project Aurion</h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding-bottom: 24px;">
                                        <div style="font-size: 1.1em; color: #444;">Your One-Time Password (OTP) is:</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding-bottom: 24px;">
                                        <div style="font-size: 2.4em; letter-spacing: 6px; font-weight: bold; color: #2563eb; background: #f1f5fb; border-radius: 8px; padding: 16px 0; width: 220px; margin: 0 auto;">{otp_code}</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding-bottom: 8px;">
                                        <div style="font-size: 1em; color: #666;">This code will expire in 5 minutes.</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding-bottom: 0;">
                                        <div style="font-size: 0.95em; color: #999;">If you did not request this, you can safely ignore this email.</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """
        return send_email(to_email, subject, html_body)


def send_html_email(to: list, subject: str, html: str, text: str = None) -> None:
    """
    Send HTML email to multiple recipients as specified in requirements.
    """
    if not to:
        raise ValueError("No recipients provided")
    
    # Use the first recipient for the main send, or send to all
    recipient = to[0] if len(to) == 1 else ", ".join(to)
    
    # Use text version if provided, otherwise extract from HTML
    if not text:
        import re
        # Simple HTML to text conversion
        text = re.sub(r'<[^>]+>', '', html)
        text = re.sub(r'\s+', ' ', text).strip()
    
    send_email(recipient, subject, text, html=html)