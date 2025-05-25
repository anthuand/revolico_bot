# Revolico Bot

## Estructura del proyecto

```
revolico_bot/
│
├── bot/                  # Lógica del bot de Telegram
│   ├── __init__.py
│   ├── handlers.py       # Handlers de comandos y mensajes
│   ├── auth.py           # Autenticación y gestión de usuarios
│   └── main.py           # Entrypoint del bot
│
├── db/                   # Acceso y modelos de base de datos
│   ├── __init__.py
│   └── core.py           # Funciones de acceso a la DB
│
├── scraper/              # Lógica de scraping
│   ├── __init__.py
│   └── revolico.py       # Scraper de Revolico
│
├── utils/                # Utilidades y helpers
│   ├── __init__.py
│   └── logger.py         # Configuración de logging
│
├── data/                 # Archivos de datos (db, logs, imágenes)
│   ├── anuncios.db
│   └── log.txt
│
├── requirements.txt
├── README.md
├── .gitignore
└── index.html
```

## Instalación y uso

1. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Configura las variables de entorno (ejemplo: `TOKEN`, `CHROMEDRIVER_PATH`, etc).
3. Ejecuta el bot:
   ```bash
   python -m bot.main
   ```

## Uso con Docker

1. Construye la imagen:
   ```bash
   docker build -t revolico-bot .
   ```
2. Ejecuta el contenedor (ajusta las variables de entorno y mounts según tu caso):
   ```bash
   docker run -d --name revolico-bot \
     -e TOKEN=tu_token_telegram \
     -e CHROMEDRIVER_PATH=/usr/local/bin/chromedriver \
     -e GOOGLE_CHROME_BIN=/usr/bin/google-chrome \
     -v $(pwd)/data:/app/data \
     revolico-bot
   ```
