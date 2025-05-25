"""
Revolico Scraper Module (Playwright version)
-------------------------------------------
Scraping robusto y profesional usando Playwright y BeautifulSoup.
Extrae anuncios publicados hace segundos, sin repeticiones, y tolerante a cambios de estructura.
"""

import os
import unicodedata
import asyncio
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from db.core import (
    create_seen_ads_table, add_seen_ad, get_seen_ads
)
from utils.logger import setup_logger
from utils.groq_client import analyze_html_with_llm

logger = setup_logger('scraper', log_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'log.txt'))

create_seen_ads_table()
seen_ads = get_seen_ads()

async def fetch_html_playwright(keyword: str) -> BeautifulSoup:
    url = f"https://www.revolico.com/search?q={keyword}&order=date"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    extra_headers = {
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.revolico.com/",
        "Connection": "keep-alive",
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--start-maximized"])
        context = await browser.new_context(
            user_agent=user_agent,
            locale="es-ES",
            extra_http_headers=extra_headers,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await page.goto(url, timeout=30000)
        await asyncio.sleep(2)
        for _ in range(3):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1)
        html = await page.content()
        if "Verify you are human" in html or "needs to review the security" in html or "cf-chl-widget" in html:
            logger.error("Cloudflare challenge detectado. El scraping fue bloqueado. Revisa debug_revolico.html para el HTML completo.")
            with open('debug_revolico.html', 'w', encoding='utf-8') as f:
                f.write(html)
            await browser.close()
            return BeautifulSoup("", "lxml")
        await browser.close()
    return BeautifulSoup(html, "lxml")

def normalize(text):
    if not text:
        return ''
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()

def get_text_from_li(li, selector, attr=None):
    el = li.select_one(selector)
    if el:
        return el.get(attr) if attr else el.get_text(strip=True)
    return ''

def extract_new_ads(soup: BeautifulSoup, keyword: str, seen_ads: Set[str]) -> List[Dict[str, str]]:
    new_ads = []
    ad_lists = soup.select('ul.sc-d225cced-2, ul, section ul, div[data-testid="ad-list"], div[data-testid="ad-list"] ul')
    if not ad_lists:
        logger.warning('No se encontró ninguna lista de anuncios (ul) en la página.')
        return []
    ad_items = [li for ad_list in ad_lists for li in ad_list.find_all('li', recursive=False)]
    if not ad_items:
        logger.warning('No se encontraron elementos <li> de anuncios en las listas detectadas.')
        return []
    keyword_norm = normalize(keyword)
    for li in ad_items:
        if li.find(class_=lambda x: x and ('Publicidad' in x or 'adsbygoogle' in x)):
            continue
        a_tag = li.find('a', href=True)
        url = a_tag['href'] if a_tag else None
        if not url or url in seen_ads:
            continue
        title = get_text_from_li(li, 'span[data-cy="adTitle"]')
        description = get_text_from_li(li, 'span[class*="Description"]')
        date = get_text_from_li(li, 'time[class*="AdMoment"]')
        price = get_text_from_li(li, 'span[data-cy="adPrice"]')
        location = get_text_from_li(li, 'span[class*="Location"]')
        img_tag = li.select_one('img')
        photo_url = img_tag['src'] if img_tag and img_tag.get('src') else ''
        if 'segundo' not in normalize(date) and 'second' not in normalize(date):
            continue
        if keyword_norm not in normalize(title) and keyword_norm not in normalize(description):
            continue
        ad = {
            'url': url,
            'title': title,
            'description': description,
            'date': date,
            'price': price,
            'location': location,
            'photo': photo_url
        }
        new_ads.append(ad)
        seen_ads.add(url)
        add_seen_ad(url)
        logger.info(f"Nuevo anuncio detectado: {title} - {url}")
    if not new_ads:
        logger.warning('No se extrajeron anuncios nuevos publicados hace segundos. Puede haber un cambio de estructura.')
    return new_ads

async def get_main_ads_playwright(keyword: str, on_new_ad=None, chat_id: Optional[int]=None, context=None) -> None:
    logger.info(f"Starting ad search for keyword: {keyword}")
    try:
        soup = await fetch_html_playwright(keyword)
        new_ads = extract_new_ads(soup, keyword, seen_ads)
        logger.info(f"Found {len(new_ads)} new ads for keyword '{keyword}'")
        for ad in new_ads:
            if on_new_ad and chat_id and context:
                on_new_ad(ad, chat_id, context)
    except Exception as e:
        logger.error(f"Error in get_main_ads_playwright: {e}", exc_info=True)

def get_main_ads(department, keyword, chat_id=None, context=None, on_new_ad=None):
    return asyncio.run(get_main_ads_playwright(keyword, on_new_ad=on_new_ad, chat_id=chat_id, context=context))

# Ejemplo de uso rápido para pruebas
if __name__ == "__main__":
    import sys
    async def main():
        keyword = sys.argv[1] if len(sys.argv) > 1 else "Aceite"
        ads = await get_main_ads(None, keyword)
        print(f"Se encontraron {len(ads)} anuncios nuevos para '{keyword}':")
        for ad in ads:
            print(ad)
    asyncio.run(main()) 