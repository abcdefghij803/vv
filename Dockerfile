FROM python:3.10-slim

# System deps
RUN apt-get update && apt-get install -y \
    ffmpeg git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Env var (bot token ayega Northflank secrets se)
ENV BOT_TOKEN=""

# Run bot
CMD ["python3", "voice_clone_bot.py"]
