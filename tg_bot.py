"""
Telegram Feedback Bot - Premium Version
=======================================
Beautiful, user-friendly Telegram bot for collecting ratings.
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

def get_question_text(first_name: str) -> str:
    """Generate personalized question text."""
    return f"""👋 Salom, {first_name}!
    
━━━━━━━━━━━━━━━━━━━━━━

📊 *Kompaniyamizni baholang*

Kompaniyamizni do'stlaringiz yoki tanishlaringizga tavsiya qilish ehtimoliyatingiz qanchalik yuqori?

━━━━━━━━━━━━━━━━━━━━━━

👋 Привет, {first_name}!

📊 *Оцените нашу компанию*

Насколько вероятно, что вы порекомендуете нашу компанию своим друзьям или знакомым?

━━━━━━━━━━━━━━━━━━━━━━

⬇️ Tanlang / Выберите оценку:"""


def get_thank_you_text(rating: int, first_name: str) -> str:
    """Generate thank you text based on rating."""
    
    if rating >= 8:
        # High rating - Promoters
        return f"""🎉 *Rahmat, {first_name}!*

━━━━━━━━━━━━━━━━━━━━━━

Sizning {rating} ⭐ bahoingiz biz uchun juda qimmatli!

Bizga ishonganingiz uchun tashakkur. Sizga eng yaxshi xizmatni taqdim etishda davom etamiz! 💙

━━━━━━━━━━━━━━━━━━━━━━

🎉 *Спасибо, {first_name}!*

Ваша оценка {rating} ⭐ очень ценна для нас!

Благодарим за доверие. Мы продолжим предоставлять вам лучший сервис! 💙"""

    elif rating >= 5:
        # Medium rating - Passives
        return f"""🙏 *Rahmat, {first_name}!*

━━━━━━━━━━━━━━━━━━━━━━

Sizning {rating} ⭐ bahoingiz uchun tashakkur!

Fikr-mulohazangiz biz uchun muhim. Xizmatlarimizni yaxshilash ustida ishlaymiz! 💪

━━━━━━━━━━━━━━━━━━━━━━

🙏 *Спасибо, {first_name}!*

Благодарим за вашу оценку {rating} ⭐!

Ваше мнение важно для нас. Мы работаем над улучшением сервиса! 💪"""

    else:
        # Low rating - Detractors
        return f"""💙 *Rahmat, {first_name}!*

━━━━━━━━━━━━━━━━━━━━━━

Sizning {rating} ⭐ bahoingiz uchun tashakkur.

Biz sizni xafa qilganimiz uchun uzr so'raymiz. Xizmatlarimizni yaxshilash uchun barcha kuchimizni sarflaymiz! 🙏

━━━━━━━━━━━━━━━━━━━━━━

💙 *Спасибо, {first_name}!*

Благодарим за вашу оценку {rating} ⭐.

Приносим извинения, если что-то пошло не так. Мы сделаем всё, чтобы стать лучше! 🙏"""


# Rating buttons in 3x3 grid
RATING_BUTTONS = [
    [("9 🌟", "9"), ("8 🔥", "8"), ("7 💎", "7")],
    [("6 😊", "6"), ("5 👍", "5"), ("4 🤔", "4")],
    [("3 😕", "3"), ("2 😞", "2"), ("1 💀", "1")],
]

# ============================================================================
# TELEGRAM API
# ============================================================================

def telegram_api(method, data):
    """Call Telegram API synchronously."""
    url = f"{TELEGRAM_API}/{method}"
    response = requests.post(url, json=data)
    return response.json()


def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Send a message."""
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return telegram_api("sendMessage", data)


def answer_callback_query(callback_query_id, text=None):
    """Answer callback query."""
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
        data["show_alert"] = False
    return telegram_api("answerCallbackQuery", data)


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
            user = message["from"]
            first_name = user.get("first_name", "друг")
            
            # Build 3x3 keyboard
            keyboard = [
                [{"text": text, "callback_data": data} for text, data in row]
                for row in RATING_BUTTONS
            ]
            reply_markup = {"inline_keyboard": keyboard}
            
            send_message(chat_id, get_question_text(first_name), reply_markup)
            logger.info(f"Sent question to user {user['id']}")
        
        # Handle callback (rating click)
        callback_query = update.get("callback_query")
        if callback_query:
            cb_id = callback_query["id"]
            user = callback_query["from"]
            rating = int(callback_query["data"])
            first_name = user.get("first_name", "друг")
            msg = callback_query["message"]
            chat_id = msg["chat"]["id"]
            message_id = msg["message_id"]
            
            # Answer callback with quick feedback
            answer_callback_query(cb_id, f"✅ {rating} ⭐ qabul qilindi!")
            
            # Remove keyboard
            edit_message_reply_markup(chat_id, message_id)
            
            # Save to sheet
            data = {
                "rating": rating,
                "name": first_name,
                "username": f"@{user['username']}" if user.get("username") else "-",
            }
            save_to_sheet(data)
            
            # Send personalized thank you
            send_message(chat_id, get_thank_you_text(rating, first_name))
            logger.info(f"Processed rating {rating} from user {user['id']}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500


if __name__ == "__main__":
    logger.info(f"Starting webhook server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
