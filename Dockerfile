FROM python:3.11-slim

# Instala dependencias del sistema recomendadas por Playwright y scraping
RUN apt-get update && apt-get install -y \
    wget curl gnupg2 \
    libnss3 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libcups2 libxss1 libxtst6 \
    libdrm2 libxfixes3 libxext6 libxshmfence1 libxinerama1 libpangoft2-1.0-0 \
    libfontconfig1 libxrender1 libxcb1 libx11-6 libxkbcommon0 \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Instala Playwright y sus navegadores
RUN pip install playwright && playwright install --with-deps

# Comando por defecto (ajusta según tu entrypoint real)
CMD ["python3", "-m", "bot.main"] 