FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Cloud Run uses PORT env variable
ENV PORT=8080

CMD ["python", "tg_bot.py"]
