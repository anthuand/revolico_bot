"""
Groq Client Utility Module
-------------------------
Provides functions to interact with Groq LLM for HTML analysis and general responses.
All code is documented and follows PEP8 and best practices.
"""

import os
from groq import Groq
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
import logging
import json
from bs4 import BeautifulSoup
import re

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SCRAPING_LLM = os.environ.get("SCRAPPING_LLM")
RESPONSES_LLM = os.environ.get("RESPONSES_LLM")

client = Groq(api_key=GROQ_API_KEY)

logger = logging.getLogger("scraper")

# Prompt robusto para extraer anuncios de HTML
PROMPT = (
    "Eres un experto en scraping. Dado el siguiente HTML de una página de resultados de anuncios de Revolico, "
    "extrae todos los anuncios publicados hace segundos (o muy recientes) que contengan el keyword proporcionado. "
    "Devuelve una lista JSON de diccionarios, cada uno con los campos: url, title, description, date, price, location, photo. "
    "No incluyas anuncios repetidos ni destacados/publicidad. "
    "Ejemplo de respuesta: ["
    "  {\"url\": \"https://...\", \"title\": \"...\", \"description\": \"...\", \"date\": \"hace 5 segundos\", \"price\": \"...\", \"location\": \"...\", \"photo\": \"...\"}, ...] "
    "Solo responde con el JSON, sin explicaciones."
)

def groq_chat_completion(messages: List[Dict[str, Any]], model: Optional[str] = None, **kwargs) -> str:
    """
    Sends a chat completion request to Groq LLM and returns the response content.
    """
    if not model:
        model = RESPONSES_LLM
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        **kwargs
    )
    return response.choices[0].message.content

def extract_relevant_html(html: str) -> str:
    """
    Extrae solo la sección relevante de anuncios del HTML (primer <ul> o <section> con anuncios).
    Si no se encuentra, recorta a 4000 caracteres.
    """
    soup = BeautifulSoup(html, "lxml")
    # Busca el primer <ul> o <section> con varios <li>
    ul = soup.find('ul')
    if ul and ul.find_all('li'):
        return str(ul)[:4000]
    section = soup.find('section')
    if section and section.find_all('li'):
        return str(section)[:4000]
    # Si no se encuentra, recorta el HTML completo
    return html[:4000]

def analyze_html_with_llm(html: str, keyword: str) -> List[Dict]:
    """
    Usa un LLM para extraer anuncios recientes del HTML de Revolico.
    Limita el tamaño del HTML para no exceder el contexto del modelo.
    """
    relevant_html = extract_relevant_html(html)
    if len(relevant_html) < len(html):
        logger.info(f"HTML reducido a {len(relevant_html)} caracteres para IA.")
    prompt = f"{PROMPT}\nKeyword: {keyword}\nHTML:\n{relevant_html}"
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=SCRAPING_LLM or "llama-3-70b-8192",
            max_tokens=2048
        )
        response_text = response.choices[0].message.content
        # Busca el primer bloque JSON en la respuesta
        start = response_text.find('[')
        end = response_text.rfind(']')
        if start == -1 or end == -1:
            logger.error("La IA no devolvió un JSON válido.")
            return []
        json_str = response_text[start:end+1]
        ads = json.loads(json_str)
        # Validar formato
        if not isinstance(ads, list):
            logger.error("La IA devolvió un formato inesperado.")
            return []
        # Limpiar y normalizar campos
        cleaned = []
        for ad in ads:
            cleaned.append({
                'url': ad.get('url', '').strip(),
                'title': ad.get('title', '').strip(),
                'description': ad.get('description', '').strip(),
                'date': ad.get('date', '').strip(),
                'price': ad.get('price', '').strip(),
                'location': ad.get('location', '').strip(),
                'photo': ad.get('photo', '').strip(),
            })
        return cleaned
    except Exception as e:
        logger.error(f"Error al analizar HTML con LLM: {e}")
        return []

def general_response_llm(prompt: str) -> str:
    """
    Uses the responses LLM to answer a general prompt.
    """
    messages = [
        {"role": "user", "content": prompt}
    ]
    return groq_chat_completion(messages, model=RESPONSES_LLM)

def escape_markdown(text: str) -> str:
    """
    Escapa caracteres especiales para Markdown V2 de Telegram.
    """
    if not text:
        return ''
    # Lista de caracteres especiales de Markdown V2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text) 