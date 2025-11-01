# backend/app/templates/email_templates.py
"""
HTML email templates for task reminders as specified in requirements.
Provides render_template function for task_otp_email.html and other email templates.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def render_template(template_name: str, **kwargs) -> str:
    """
    Render email template with provided context variables.
    Matches the render_template function used in the Celery worker.
    """
    if template_name == "task_otp_email.html":
        return render_task_otp_email(**kwargs)
    elif template_name == "task_reminder_email.html":
        return render_task_reminder_email(**kwargs)
    elif template_name == "task_completion_email.html":
        return render_task_completion_email(**kwargs)
    elif template_name == "task_creation_email.html":
        return render_task_creation_email(**kwargs)
    elif template_name == "task_update_email.html":
        return render_task_update_email(**kwargs)
    elif template_name == "welcome_email.html":
        return render_welcome_email(**kwargs)
    else:
        logger.warning(f"Unknown template: {template_name}")
        return f"<html><body><p>Template {template_name} not found</p></body></html>"


def render_task_otp_email(title: str, otp: str, user_email: str, **kwargs) -> str:
    """
    Render the main task OTP email template as specified in requirements.
    This is the template used in the Celery worker send_task_otp_task.
    """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Reminder - {title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .task-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 20px;
                text-align: center;
            }}
            .otp-container {{
                background-color: #f3f4f6;
                border: 2px dashed #d1d5db;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                margin: 20px 0;
            }}
            .otp-code {{
                font-size: 32px;
                font-weight: 700;
                color: #059669;
                letter-spacing: 4px;
                font-family: 'Courier New', monospace;
                margin: 10px 0;
            }}
            .otp-label {{
                font-size: 14px;
                color: #6b7280;
                margin-bottom: 10px;
            }}
            .expiry-notice {{
                background-color: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 15px;
                margin: 20px 0;
                border-radius: 4px;
            }}
            .expiry-notice p {{
                margin: 0;
                color: #92400e;
                font-weight: 500;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .aurion-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">⏰</span> Task Reminder</h1>
            </div>
            
            <div class="content">
                <div class="task-title">
                    {title}
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 30px;">
                    Hello! 👋 This is your scheduled reminder.
                </p>
                
                <div class="otp-container">
                    <div class="otp-label">Your verification code:</div>
                    <div class="otp-code">{otp}</div>
                </div>
                
                <div class="expiry-notice">
                    <p><strong>⏱️ Important:</strong> This code will expire in 10 minutes for security reasons.</p>
                </div>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 30px;">
                    You can use this code to verify the reminder or simply ignore this email if you've already completed the task.
                </p>
            </div>
            
            <div class="footer">
                <p>
                    <span class="aurion-logo">Aurion AI</span> 💫 - Your Personal Assistant<br>
                    <small>This reminder was automatically generated based on your request.</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_task_reminder_email(title: str, due_date: Optional[datetime] = None, description: Optional[str] = None, **kwargs) -> str:
    """
    Render a simple task reminder email (without OTP).
    """
    due_date_str = "No specific time" if not due_date else due_date.strftime("%B %d, %Y at %I:%M %p")
    description_text = description or "No additional details provided."
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Reminder - {title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .task-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 20px;
                text-align: center;
            }}
            .task-details {{
                background-color: #f3f4f6;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .detail-row {{
                display: flex;
                margin-bottom: 10px;
            }}
            .detail-label {{
                font-weight: 600;
                color: #374151;
                min-width: 80px;
            }}
            .detail-value {{
                color: #6b7280;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .maya-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">📋</span> Task Reminder</h1>
            </div>
            
            <div class="content">
                <div class="task-title">
                    {title}
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 30px;">
                    Hello! 👋 This is your scheduled reminder.
                </p>
                
                <div class="task-details">
                    <div class="detail-row">
                        <div class="detail-label">Time:</div>
                        <div class="detail-value">{due_date_str}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">Details:</div>
                        <div class="detail-value">{description_text}</div>
                    </div>
                </div>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 30px;">
                    This reminder was automatically generated based on your request.
                </p>
            </div>
            
            <div class="footer">
                <p>
                    <span class="maya-logo">Maya AI</span> 💫 - Your Personal Assistant<br>
                    <small>Stay productive and organized!</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_task_completion_email(title: str, completed_at: Optional[datetime] = None, **kwargs) -> str:
    """
    Render a task completion confirmation email.
    """
    completed_at_str = completed_at.strftime("%B %d, %Y at %I:%M %p") if completed_at else "Just now"
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Completed - {title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #059669 0%, #047857 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .task-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 20px;
                text-align: center;
            }}
            .completion-badge {{
                background-color: #d1fae5;
                border: 2px solid #10b981;
                border-radius: 50px;
                padding: 15px 30px;
                text-align: center;
                margin: 20px 0;
                color: #047857;
                font-weight: 600;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .maya-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">✅</span> Task Completed</h1>
            </div>
            
            <div class="content">
                <div class="task-title">
                    {title}
                </div>
                
                <div class="completion-badge">
                    <span class="emoji">🎉</span> Great job! Task completed successfully
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 20px;">
                    Completed on: {completed_at_str}
                </p>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 30px;">
                    Keep up the great work! Your productivity is on track.
                </p>
            </div>
            
            <div class="footer">
                <p>
                    <span class="maya-logo">Maya AI</span> 💫 - Your Personal Assistant<br>
                    <small>Celebrating your achievements!</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_task_creation_email(title: str, description: str, due_date: Optional[str] = None, 
                              priority: str = "medium", task_id: str = None, **kwargs) -> str:
    """
    Render a task creation notification email.
    """
    priority_colors = {
        "low": "#10b981",
        "medium": "#f59e0b", 
        "high": "#ef4444",
        "urgent": "#dc2626"
    }
    priority_color = priority_colors.get(priority.lower(), "#6b7280")
    due_date_str = due_date or "No specific due date"
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Task Created - {title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .task-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 20px;
                text-align: center;
            }}
            .task-details {{
                background-color: #f3f4f6;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .detail-row {{
                display: flex;
                margin-bottom: 10px;
            }}
            .detail-label {{
                font-weight: 600;
                color: #374151;
                min-width: 80px;
            }}
            .detail-value {{
                color: #6b7280;
            }}
            .priority-badge {{
                display: inline-block;
                background-color: {priority_color};
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .maya-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">📝</span> New Task Created</h1>
            </div>
            
            <div class="content">
                <div class="task-title">
                    {title}
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 30px;">
                    A new task has been added to your task list.
                </p>
                
                <div class="task-details">
                    <div class="detail-row">
                        <div class="detail-label">Description:</div>
                        <div class="detail-value">{description}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">Due Date:</div>
                        <div class="detail-value">{due_date_str}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">Priority:</div>
                        <div class="detail-value">
                            <span class="priority-badge">{priority.upper()}</span>
                        </div>
                    </div>
                    {f'<div class="detail-row"><div class="detail-label">Task ID:</div><div class="detail-value">{task_id}</div></div>' if task_id else ''}
                </div>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 30px;">
                    You'll receive reminders based on your task settings.
                </p>
            </div>
            
            <div class="footer">
                <p>
                    <span class="maya-logo">Maya AI</span> 💫 - Your Personal Assistant<br>
                    <small>Stay organized and productive!</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_task_update_email(title: str, description: str, due_date: Optional[str] = None, 
                            priority: str = "medium", **kwargs) -> str:
    """
    Render a task update notification email.
    """
    priority_colors = {
        "low": "#10b981",
        "medium": "#f59e0b", 
        "high": "#ef4444",
        "urgent": "#dc2626"
    }
    priority_color = priority_colors.get(priority.lower(), "#6b7280")
    due_date_str = due_date or "No specific due date"
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Updated - {title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .task-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 20px;
                text-align: center;
            }}
            .task-details {{
                background-color: #f3f4f6;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .detail-row {{
                display: flex;
                margin-bottom: 10px;
            }}
            .detail-label {{
                font-weight: 600;
                color: #374151;
                min-width: 80px;
            }}
            .detail-value {{
                color: #6b7280;
            }}
            .priority-badge {{
                display: inline-block;
                background-color: {priority_color};
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .maya-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">✏️</span> Task Updated</h1>
            </div>
            
            <div class="content">
                <div class="task-title">
                    {title}
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 30px;">
                    This task has been updated with new information.
                </p>
                
                <div class="task-details">
                    <div class="detail-row">
                        <div class="detail-label">Description:</div>
                        <div class="detail-value">{description}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">Due Date:</div>
                        <div class="detail-value">{due_date_str}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">Priority:</div>
                        <div class="detail-value">
                            <span class="priority-badge">{priority.upper()}</span>
                        </div>
                    </div>
                </div>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center; margin-top: 30px;">
                    Check your task list for the latest updates.
                </p>
            </div>
            
            <div class="footer">
                <p>
                    <span class="maya-logo">Maya AI</span> 💫 - Your Personal Assistant<br>
                    <small>Keep your tasks up to date!</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_welcome_email(user_name: Optional[str] = None, **kwargs) -> str:
    """
    Render a welcome email for new users.
    """
    greeting = f"Hello {user_name}!" if user_name else "Hello!"
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to Maya AI</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                color: #111827;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
                color: white;
                padding: 40px 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: 700;
            }}
            .content {{
                padding: 40px 30px;
            }}
            .welcome-text {{
                font-size: 18px;
                color: #1f2937;
                margin-bottom: 30px;
                text-align: center;
            }}
            .features {{
                margin: 30px 0;
            }}
            .feature {{
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                padding: 15px;
                background-color: #f8fafc;
                border-radius: 8px;
            }}
            .feature-icon {{
                font-size: 24px;
                margin-right: 15px;
            }}
            .feature-text {{
                color: #374151;
            }}
            .cta-button {{
                display: inline-block;
                background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
                color: white;
                padding: 15px 30px;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                text-align: center;
                margin: 20px 0;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 30px;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}
            .footer p {{
                margin: 0;
                color: #6b7280;
                font-size: 14px;
            }}
            .maya-logo {{
                color: #8b5cf6;
                font-weight: 600;
            }}
            .emoji {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji">🌟</span> Welcome to Maya AI</h1>
            </div>
            
            <div class="content">
                <div class="welcome-text">
                    {greeting} We're excited to have you on board!
                </div>
                
                <p style="text-align: center; color: #6b7280; margin-bottom: 30px;">
                    Your personal AI assistant is ready to help you stay organized and productive.
                </p>
                
                <div class="features">
                    <div class="feature">
                        <div class="feature-icon">⏰</div>
                        <div class="feature-text">
                            <strong>Smart Reminders:</strong> Set reminders with natural language and receive OTP-verified notifications
                        </div>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">🤖</div>
                        <div class="feature-text">
                            <strong>AI-Powered:</strong> Intelligent task management with context-aware suggestions
                        </div>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">📱</div>
                        <div class="feature-text">
                            <strong>Cross-Platform:</strong> Access your tasks from anywhere, anytime
                        </div>
                    </div>
                </div>
                
                <div style="text-align: center;">
                    <a href="#" class="cta-button">Get Started</a>
                </div>
            </div>
            
            <div class="footer">
                <p>
                    <span class="maya-logo">Maya AI</span> 💫 - Your Personal Assistant<br>
                    <small>Ready to transform your productivity!</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
