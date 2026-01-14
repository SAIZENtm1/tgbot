# Telegram Feedback Bot 🤖

Production-ready Telegram bot for collecting user ratings with Google Sheets integration.

## Features
- ✅ Bilingual interface (Uzbek + Russian)
- ✅ 9-star rating system with inline buttons
- ✅ Google Sheets data storage
- ✅ Deduplication (no duplicate entries)
- ✅ Async for high performance
- ✅ Proper error handling and logging

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Create Telegram Bot
1. Message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Copy the token

### 3. Google Sheets Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable Google Sheets API
3. Create Service Account → Download JSON credentials → rename to `credentials.json`
4. Create a Google Sheet with headers:
   ```
   timestamp | rating | user_id | username | first_name | last_name | full_name | chat_id | message_id | update_id
   ```
5. Share the sheet with your service account email (found in `credentials.json`)

### 4. Configure Environment
```bash
export BOT_TOKEN="your_bot_token"
export SPREADSHEET_ID="your_spreadsheet_id"
export GOOGLE_CREDENTIALS_FILE="credentials.json"
```

Or edit the constants directly in `tg_bot.py`.

### 5. Run
```bash
python tg_bot.py
```

## Flow
1. User sends `/start`
2. Bot shows bilingual question with 9 rating buttons
3. User clicks a rating
4. Bot removes buttons, saves to Sheet, sends thank you message

## Deployment (Production)
For production, use systemd, Docker, or a process manager like PM2/Supervisor.

```bash
# Example with nohup
nohup python tg_bot.py > bot.log 2>&1 &
```
