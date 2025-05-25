FROM python:3.11-slim

# Instalar dependencias del sistema para Raspberry Pi
RUN apt-get update && \
    apt-get install -y chromium-browser chromium-chromedriver && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV CHROMEDRIVER_PATH=/usr/lib/chromium-browser/chromedriver
ENV GOOGLE_CHROME_BIN=/usr/bin/chromium-browser

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "-m", "bot.main"] 