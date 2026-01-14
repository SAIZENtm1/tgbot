"""
Telegram Feedback Bot - Cloud Run Webhook Version
==================================================
Production-ready Telegram bot for collecting user ratings.
Uses webhook mode for serverless deployment (Railway/Cloud Run).
"""

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
TIMEZONE = ZoneInfo("Asia/Tashkent")
PORT = int(os.getenv("PORT", 8080))
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================================
# TEXTS
# ============================================================================

QUESTION_TEXT = (
    "Komрaniyamizni do'stlaringiz yoki tanishlaringizga tavsiya qilish "
    "ehtimolingiz qanchalik yuqori?\n\n"
    "Насколько вероятно, что вы порекомендуете нашу компанию своим "
    "друзьям или знакомым?"
)

THANK_YOU_TEXT = (
    "Qimmatli vaqtingizni ajratib fikringizni bildirganingiz uchun tashakkur!\n"
    "Sizning bahoingiz biz uchun juda muhim va xizmatlarimizni yanada "
    "yaxshilashga yordam beradi.Sizga yanada yaxshi tajriba taqdim etish "
    "uchun doim harakatdamiz! 💙\n\n"
    "Благодарим вас за то, что нашли время поделиться своим мнением!\n"
    "Ваша оценка очень важна для нас и помогает нам становиться лучше."
    "Мы всегда стремимся предоставить вам лучший сервис! 💙"
)

RATING_BUTTONS = [
    ("9 🌟", "9"),
    ("8 🔥", "8"),
    ("7 💎", "7"),
    ("6 😊", "6"),
    ("5 👍", "5"),
    ("4 🤔", "4"),
    ("3 😕", "3"),
    ("2 😞", "2"),
    ("1 💀", "1"),
]

# ============================================================================
# TELEGRAM API (synchronous)
# ============================================================================

def telegram_api(method, data):
    """Call Telegram API synchronously."""
    url = f"{TELEGRAM_API}/{method}"
    response = requests.post(url, json=data)
    return response.json()


def send_message(chat_id, text, reply_markup=None):
    """Send a message."""
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return telegram_api("sendMessage", data)


def answer_callback_query(callback_query_id):
    """Answer callback query."""
    return telegram_api("answerCallbackQuery", {"callback_query_id": callback_query_id})


def edit_message_reply_markup(chat_id, message_id):
    """Remove inline keyboard."""
    return telegram_api("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": None
    })


# ============================================================================
# GOOGLE SHEETS
# ============================================================================

_sheets_client = None
_processed_updates: set[int] = set()


def get_sheets_client():
    """Initialize Google Sheets client with caching."""
    global _sheets_client
    if _sheets_client is None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        
        google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if google_creds_json:
            creds_dict = json.loads(google_creds_json)
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE, scopes=scopes
            )
        
        _sheets_client = gspread.authorize(credentials)
    return _sheets_client


def save_to_sheet(data: dict) -> bool:
    """Save rating data to Google Sheets."""
    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = spreadsheet.sheet1
        
        timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        
        row = [
            timestamp,
            data["rating"],
            data["name"],
            data["username"],
        ]
        
        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"Saved rating {data['rating']} from {data['username']}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save to sheet: {e}")
        return False


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)


@app.route("/", methods=["GET"])
def health():
    """Health check endpoint."""
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates."""
    try:
        update = request.get_json()
        update_id = update.get("update_id")
        
        # Deduplication
        if update_id in _processed_updates:
            return "OK", 200
        _processed_updates.add(update_id)
        
        # Cleanup old IDs
        if len(_processed_updates) > 10000:
            oldest = sorted(_processed_updates)[:5000]
            for old_id in oldest:
                _processed_updates.discard(old_id)
        
        # Handle /start
        message = update.get("message")
        if message and message.get("text") == "/start":
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            
            keyboard = [[{"text": text, "callback_data": data}] for text, data in RATING_BUTTONS]
            reply_markup = {"inline_keyboard": keyboard}
            
            send_message(chat_id, QUESTION_TEXT, reply_markup)
            logger.info(f"Sent question to user {user_id}")
        
        # Handle callback (rating click)
        callback_query = update.get("callback_query")
        if callback_query:
            cb_id = callback_query["id"]
            user = callback_query["from"]
            rating = callback_query["data"]
            msg = callback_query["message"]
            chat_id = msg["chat"]["id"]
            message_id = msg["message_id"]
            
            # Answer callback
            answer_callback_query(cb_id)
            
            # Remove keyboard
            edit_message_reply_markup(chat_id, message_id)
            
            # Save to sheet
            data = {
                "rating": rating,
                "name": user.get("first_name", "-"),
                "username": f"@{user['username']}" if user.get("username") else "-",
            }
            save_to_sheet(data)
            
            # Send thank you
            send_message(chat_id, THANK_YOU_TEXT)
            logger.info(f"Processed rating {rating} from user {user['id']}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500


if __name__ == "__main__":
    logger.info(f"Starting webhook server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
