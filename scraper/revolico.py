"""
Revolico Scraper Module
----------------------
Provides functions to scrape and process ads from Revolico using Selenium and BeautifulSoup.
All code is documented and follows PEP8 and best practices.
"""

import os
import time
import requests
import unicodedata
from typing import List, Dict, Optional, Set, Tuple
from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from db.core import (
    create_ads_table, insert_ad, create_seen_ads_table, add_seen_ad, get_seen_ads
)
from utils.logger import setup_logger
from utils.groq_client import analyze_html_with_llm

logger = setup_logger('scraper', log_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'log.txt'))

# Initialize tables and load seen ads
create_seen_ads_table()
seen_ads = get_seen_ads()

def get_webdriver() -> webdriver.Chrome:
    """
    Initializes and returns a configured Selenium Chrome WebDriver.
    """
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/chromium-browser")
    options = webdriver.ChromeOptions()
    options.binary_location = chrome_bin
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--headless")
    options.add_argument("--window-size=1280,800")
    options.add_argument('blink-settings=imagesEnabled=false')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.53 Safari/537.36'})
    return driver

def scroll_page(driver: webdriver.Chrome, step: int = 250, delay: float = 1.0) -> None:
    """
    Scrolls down the page incrementally to load dynamic content.
    """
    iteration = 1
    while True:
        scroll_height = driver.execute_script("return document.documentElement.scrollHeight")
        height = step * iteration
        driver.execute_script(f"window.scrollTo(0, {height});")
        if height > scroll_height:
            break
        time.sleep(delay)
        iteration += 1

def extract_new_ads(soup: BeautifulSoup, keyword: str, seen_ads: Set[str]) -> List[Dict[str, str]]:
    """
    Extracts new ads from the parsed HTML soup that match the keyword and are not in seen_ads.
    """
    new_ads = []
    ul = soup.find('ul')
    if not ul:
        logger.warning('Could not find the ad list (ul) in the page.')
        return []
    for li in ul.find_all('li'):
        try:
            a_tag = li.find('a')
            url = a_tag.get('href') if a_tag else None
            if not url or url in seen_ads:
                continue
            title_tag = li.find('span', {'data-cy': 'adTitle'})
            title = title_tag.get_text(strip=True) if title_tag else ''
            desc_tag = li.find('span', {'class': lambda x: x and 'Description' in x})
            description = desc_tag.get_text(strip=True) if desc_tag else ''
            date_tag = li.find('time', {'class': lambda x: x and 'AdMoment' in x})
            date = date_tag.get_text(strip=True) if date_tag else ''
            price_tag = li.find('span', {'data-cy': 'adPrice'})
            price = price_tag.get_text(strip=True) if price_tag else ''
            if not price:
                logger.warning(f"No price found for ad: {title} - {url}")
            location_tag = li.find('span', {'class': lambda x: x and 'Location' in x})
            location = location_tag.get_text(strip=True) if location_tag else ''
            if not location:
                logger.warning(f"No location found for ad: {title} - {url}")
            photo_url = ''
            photo_tag = li.find('img')
            if photo_tag and photo_tag.get('src'):
                photo_url = photo_tag.get('src')
            else:
                a_photo = li.find('a', {'class': lambda x: x and 'ADRO' in x})
                if a_photo and a_photo.get('href'):
                    photo_url = a_photo.get('href')
            if not photo_url:
                logger.warning(f"No photo found for ad: {title} - {url}")
            if 'seconds' not in date:
                continue
            keyword_norm = unicodedata.normalize('NFKD', keyword).encode('ASCII', 'ignore').decode('utf-8').lower()
            title_norm = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('utf-8').lower()
            description_norm = unicodedata.normalize('NFKD', description).encode('ASCII', 'ignore').decode('utf-8').lower()
            if keyword_norm in title_norm or keyword_norm in description_norm:
                logger.info(f"New ad detected: {title} - {url}")
                new_ads.append({
                    'url': url,
                    'title': title,
                    'description': description,
                    'date': date,
                    'price': price,
                    'location': location,
                    'photo': photo_url
                })
                seen_ads.add(url)
                add_seen_ad(url)
        except Exception as e:
            logger.error(f"Error processing ad: {e}")
            continue
    return new_ads

def get_images(url: str) -> Optional[str]:
    """
    Downloads the main image from the ad page and returns its URL.
    """
    driver = get_webdriver()
    driver.get(url)
    driver.implicitly_wait(0.3)
    scroll_page(driver)
    body = driver.execute_script("return document.body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")
    driver.quit()
    image_container = soup.find('div', {'class': 'Detail__ImagesWrapper-sc-1irc1un-8 hImDlm'})
    if image_container:
        images = image_container.find_all('div')
        for image in images:
            a_tag = image.find('a')
            if a_tag and a_tag.get('href'):
                url = a_tag.get('href')
        img_response = requests.get(url)
        with open('photo.jpg', 'wb') as f:
            f.write(img_response.content)
        return url
    return None

def get_contact_info(url: str) -> Tuple[str, str, str]:
    """
    Extracts contact name, phone, and email from the ad page.
    """
    driver = get_webdriver()
    driver.get(url)
    driver.implicitly_wait(0.3)
    scroll_page(driver)
    body = driver.execute_script("return document.body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")
    contact = soup.find('div', {'data-cy': 'adName'}).get_text() if soup.find('div', {'data-cy': 'adName'}) else "not available"
    phone = soup.find('a', {'data-cy': 'adPhone'}).get_text() if soup.find('a', {'data-cy': 'adPhone'}) else "not available"
    email = soup.find('a', {'data-cy': 'adEmail'}).get_text() if soup.find('a', {'data-cy': 'adEmail'}) else "not available"
    driver.quit()
    return contact, phone, email

def fetch_html(
    department: Optional[str], keyword: str, price_min: Optional[int] = None, price_max: Optional[int] = None,
    province: Optional[str] = None, municipality: Optional[str] = None, photos: Optional[bool] = None
) -> BeautifulSoup:
    """
    Loads the search results page for the given keyword and returns a BeautifulSoup object.
    """
    driver = get_webdriver()
    url = f"https://www.revolico.com/search?q={keyword}&order=date"
    driver.get(url)
    driver.set_window_size(1280, 800)
    driver.implicitly_wait(0.1)
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Buscar')]"))
        )
    except Exception as e:
        logger.error(f"Search button not found: {e}")
        with open('debug_revolico.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    scroll_page(driver)
    body = driver.find_element(By.TAG_NAME, "body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")
    driver.quit()
    return soup

def get_main_ads(
    department: Optional[str], keyword: str, price_min: Optional[int] = None, price_max: Optional[int] = None,
    province: Optional[str] = None, municipality: Optional[str] = None, photos: Optional[bool] = None,
    chat_id: Optional[int] = None, context=None, on_new_ad=None
) -> None:
    """
    Main entry point to search for new ads and process them (optionally sending to a callback).
    """
    logger.info(f"Starting ad search for keyword: {keyword}")
    try:
        web_content = fetch_html(department, keyword, price_min, price_max, province, municipality, photos)
        html = str(web_content)
        query_llm = (
            f"Extract all ads published seconds ago related to '{keyword}'. "
            "Return a JSON list with the fields: url, title, description, date, price, location, photo."
        )
        try:
            import json
            llm_result = analyze_html_with_llm(html, query_llm)
            ads_llm = json.loads(llm_result)
            logger.info(f"LLM returned {len(ads_llm)} ads for keyword '{keyword}'")
        except Exception as e:
            logger.error(f"Error using LLM to analyze HTML: {e}", exc_info=True)
            ads_llm = []
        new_ads = []
        for ad in ads_llm:
            url = ad.get('url')
            if url and url not in seen_ads:
                new_ads.append(ad)
                seen_ads.add(url)
                add_seen_ad(url)
                if on_new_ad and chat_id and context:
                    on_new_ad(ad, chat_id, context)
        logger.info(f"Found {len(new_ads)} new ads for keyword '{keyword}'")
    except Exception as e:
        logger.error(f"Error in get_main_ads: {e}", exc_info=True) 