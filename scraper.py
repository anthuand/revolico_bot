import os
import time
import logging
import requests # Not directly used for scraping but kept for potential future image download
import unicodedata
import random 
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Assuming db.py is in the same directory or accessible in PYTHONPATH
import db 

# Configure logging
# BasicConfig should ideally be called once at the application entry point (e.g., main.py).
# If scraper.py is run standalone, this is fine. If imported, it might conflict or be redundant.
# For this task, we'll keep it to allow standalone testing.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- WebDriver Management ---
_driver_instance = None # This global instance is managed by get_webdriver_instance and close_webdriver

def get_webdriver_instance():
    """
    Creates and returns a single WebDriver instance.
    If an instance already exists, it returns the existing one.
    """
    global _driver_instance
    if _driver_instance is None:
        options = webdriver.ChromeOptions()
        options.add_argument("start-maximized")
        options.add_argument('blink-settings=imagesEnabled=false') 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage") 
        options.add_argument("--headless") 
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")

        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "chromedriver")
        
        try:
            _driver_instance = webdriver.Chrome(executable_path=chromedriver_path, options=options)
            
            _driver_instance.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            })
            _driver_instance.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            _driver_instance.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
            })
            logger.info(f"WebDriver initialized. User Agent: {_driver_instance.execute_script('return navigator.userAgent;')}")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}", exc_info=True)
            _driver_instance = None # Ensure it's None if initialization failed
            raise
    return _driver_instance

def close_webdriver():
    """Closes the WebDriver instance if it exists and clears the global reference."""
    global _driver_instance
    if _driver_instance is not None:
        try:
            _driver_instance.quit()
            logger.info("WebDriver closed successfully.")
        except Exception as e:
            logger.error(f"Error closing WebDriver: {e}", exc_info=True)
        finally:
            _driver_instance = None # Clear the global reference

# --- Helper Functions ---
def scroll_to_bottom(driver):
    """Scrolls to the bottom of the page."""
    try:
        logger.debug("Scrolling to bottom of the page.")
        last_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(1.5, 2.5)) 

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height > last_height:
            logger.debug("Page height increased after scroll.")
        else:
            logger.debug("Scrolled to bottom. Page height did not change significantly.")
    except Exception as e:
        logger.warning(f"Error during scrolling: {e}", exc_info=True)

def get_soup(driver, url=None, is_new_navigation=True):
    """
    Navigates to a URL (if provided & is_new_navigation=True) and returns BeautifulSoup object.
    """
    try:
        if url and is_new_navigation:
            logger.debug(f"Fetching page source for URL: {url}")
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body"))) 
            time.sleep(random.uniform(1.0, 2.0)) # Shorter delay after explicit navigation
        elif not is_new_navigation:
             logger.debug("Getting source from current page (no new navigation).")
             time.sleep(random.uniform(0.5, 1.0))
        else: 
            logger.debug("Getting source from current page.")
            time.sleep(random.uniform(0.5, 1.0))

        source = driver.page_source
        soup = BeautifulSoup(source, "lxml")
        return soup
    except TimeoutException:
        logger.error(f"Timeout waiting for page to load: {url if url else 'current page'}")
        return None
    except Exception as e:
        logger.error(f"Error getting BeautifulSoup object for {url if url else 'current page'}: {e}", exc_info=True)
        return None

# --- Main Scraping Logic ---

def obtener_imagenes_de_anuncio(driver, ad_url):
    """Obtains image URLs from a specific ad page."""
    logger.info(f"Obtaining images from ad URL: {ad_url}")
    soup = get_soup(driver, ad_url, is_new_navigation=True)
    if not soup:
        return []

    image_urls = []
    try:
        image_container = soup.find('div', class_='Detail__ImagesWrapper-sc-1irc1un-8 hImDlm')
        if image_container:
            image_links = image_container.find_all('a', href=True)
            for link_tag in image_links:
                href = link_tag.get('href')
                if href and (href.lower().endswith('.jpg') or href.lower().endswith('.png') or href.lower().endswith('.jpeg')):
                    image_urls.append(href) # Assuming absolute URLs
            logger.info(f"Found {len(image_urls)} image link(s) for ad: {ad_url}.")
        else:
            logger.warning(f"No image container found for ad: {ad_url}")
    except Exception as e:
        logger.error(f"Error extracting images from {ad_url}: {e}", exc_info=True)
    return image_urls


def obtener_contacto_de_anuncio(driver, ad_url):
    """Obtains contact information from a specific ad page."""
    logger.info(f"Obtaining contact info from ad URL: {ad_url}")
    soup = get_soup(driver, ad_url, is_new_navigation=True)
    if not soup:
        return "no tiene", "no tiene", "no tiene"

    contacto, telefono, email = "no tiene", "no tiene", "no tiene"
    try:
        contacto_tag = soup.find('div', {'data-cy': 'adName'})
        if contacto_tag: contacto = contacto_tag.get_text(strip=True)

        telefono_tag = soup.find('a', {'data-cy': 'adPhone'})
        if telefono_tag: telefono = telefono_tag.get_text(strip=True)

        email_tag = soup.find('a', {'data-cy': 'adEmail'})
        if email_tag: email = email_tag.get_text(strip=True)
        
        logger.info(f"Contact info for {ad_url}: Name='{contacto}', Phone='{telefono}', Email='{email}'")
    except Exception as e:
        logger.error(f"Error extracting contact info from {ad_url}: {e}", exc_info=True)
    return contacto, telefono, email


def buscar_anuncios(driver, db_conn, departamento=None, palabra_clave=None, precio_min=None, precio_max=None, provincia=None, municipio=None, fotos=None, max_pages=5):
    """
    Searches for ads, handles pagination, and calls processing function.
    `db_conn` is the database connection passed from the caller (e.g., main.py's thread).
    """
    base_url = "https://www.revolico.com/"
    search_path = "search.html"
    query_params = {'order': 'date'} # Default order

    if departamento: base_url = f"{base_url}{departamento}/"
    if palabra_clave: query_params['q'] = palabra_clave
    
    current_url = f"{base_url}{search_path}"
    if query_params: current_url += "?" + "&".join([f"{k}={v}" for k, v in query_params.items()])

    logger.info(f"Accessing initial search URL: {current_url}")
    driver.get(current_url)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(random.uniform(1.0, 2.0)) 

    filters_applied_this_session = False
    if any([precio_min, precio_max, provincia, municipio, fotos]):
        try:
            logger.info("Attempting to apply search filters...")
            if precio_min is not None:
                min_price_input = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name*='minPrice'], input[placeholder*='mínimo'], input[data-cy='minPriceInput']")))
                min_price_input.clear()
                min_price_input.send_keys(str(precio_min))
                logger.info(f"Set precio_min: {precio_min}")
                time.sleep(random.uniform(0.2, 0.5))

            if precio_max is not None:
                max_price_input = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name*='maxPrice'], input[placeholder*='máximo'], input[data-cy='maxPriceInput']")))
                max_price_input.clear()
                max_price_input.send_keys(str(precio_max))
                logger.info(f"Set precio_max: {precio_max}")
                time.sleep(random.uniform(0.2, 0.5))

            if provincia is not None:
                provincia_select_el = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, "select[name*='province'], select[data-cy='provinceSelect']")))
                select = Select(provincia_select_el)
                select.select_by_visible_text(provincia)
                logger.info(f"Selected provincia: {provincia}")
                time.sleep(random.uniform(0.2, 0.5))
            
            search_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], button[data-cy='searchButton'], button[class*='SearchForm__SubmitButton']")))
            search_button.click()
            logger.info("Applied filters and submitted search.")
            filters_applied_this_session = True
            time.sleep(random.uniform(1.0, 2.0)) 
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul[class*='List'], div[data-cy*='resultsContainer']")))
            logger.info("Search results page loaded after filter application.")
        except Exception as e: # Catching broader exceptions during filter application
            logger.error(f"Error applying filters: {e}. Proceeding with current page if possible.", exc_info=True)
    
    for page_num in range(1, max_pages + 1):
        logger.info(f"--- Processing page {page_num} (URL: {driver.current_url}) ---")
        
        if page_num > 1 or not filters_applied_this_session: # If it's not the first page, or if it is but no filters were applied (so page is fresh)
             time.sleep(random.uniform(0.5, 1.5)) 
        
        scroll_to_bottom(driver) 
        current_page_soup = get_soup(driver, is_new_navigation=False) 
        
        if current_page_soup:
            # Pass db_conn here
            procesar_y_guardar_anuncios(current_page_soup, palabra_clave, db_conn)
        else:
            logger.error(f"Could not get page source for page {page_num}. Skipping.")

        if page_num == max_pages:
            logger.info(f"Reached max_pages limit of {max_pages}. Stopping pagination for this filter run.")
            break
        try:
            next_page_button_xpath = "//a[normalize-space()='Siguiente' or normalize-space()='Next' or contains(@title, 'Siguiente') or contains(@title, 'Next') or contains(normalize-space(@class), 'next') or contains(normalize-space(@class), 'pagination-next') or @rel='next' or contains(@aria-label,'Siguiente') or contains(@aria-label,'Next')]"
            next_page_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, next_page_button_xpath))
            )
            logger.info("Found 'Next Page' button. Clicking...")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_page_button) 
            time.sleep(random.uniform(0.3, 0.7)) 
            next_page_button.click()
            
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul[class*='List'], div[data-cy*='resultsContainer']"))) 
            logger.info(f"Successfully navigated to page {page_num + 1} (approx).")
            filters_applied_this_session = False # Reset flag after first successful navigation
        except TimeoutException:
            logger.info(f"No 'Next Page' button found or clickable after {page_num} page(s). Concluding pagination for this filter run.")
            break
        except Exception as e:
            logger.error(f"An error occurred during pagination: {e}. Concluding pagination for this filter run.", exc_info=True)
            break
        time.sleep(random.uniform(1.0, 2.5)) 
    logger.info(f"Finished searching for filter '{palabra_clave}'.")


def procesar_y_guardar_anuncios(soup, palabra_clave, db_conn):
    """
    Processes ads from BeautifulSoup soup, inserts them using db_conn.
    Returns count of newly inserted ads.
    """
    if not soup:
        logger.warning("No soup object to process for ads.")
        return 0 
    if not db_conn:
        logger.error("Database connection not provided to procesar_y_guardar_anuncios. Cannot save ads.")
        return 0

    anuncios_container = soup.find('ul') 
    if not anuncios_container or not anuncios_container.find_all('li', recursive=False): 
        logger.debug("Initial 'ul' not suitable/empty. Trying specific classes/data-cy.")
        anuncios_container = soup.find('ul', class_=lambda x: x and ('List' in x or 'Results' in x))
        if not anuncios_container:
            anuncios_container = soup.find('div', {'data-cy': lambda x: x and 'results' in x.lower()})

    newly_inserted_ads_count = 0
    if anuncios_container:
        item_tag_type = 'li'
        articulos = anuncios_container.find_all(item_tag_type, recursive=False)
        if not articulos: 
            item_tag_type = 'div'
            articulos = anuncios_container.find_all(item_tag_type, recursive=False)

        logger.info(f"Found {len(articulos)} potential ad items (tag '{item_tag_type}') in container.")
        
        for i, articulo in enumerate(articulos):
            try:
                url_tag = articulo.find('a', href=True)
                url = url_tag['href'] if url_tag else 'no tiene'
                if url != 'no tiene':
                    if not url.startswith('http'): url = "https://www.revolico.com" + url 
                    if "/item/" not in url: continue 

                titulo_tag = articulo.find('span', {'data-cy': 'adTitle'})
                titulo = titulo_tag.get_text(strip=True) if titulo_tag else (url_tag.get_text(strip=True) if url_tag else 'no tiene')
                if not titulo or titulo == 'no tiene': # Try harder to find a title if data-cy fails
                    h_tag = articulo.find(['h1', 'h2', 'h3', 'div'], class_=lambda x: x and "title" in x.lower())
                    if h_tag : titulo = h_tag.get_text(strip=True)
                
                precio_tag = articulo.find('span', {'data-cy': 'adPrice'})
                precio = precio_tag.get_text(strip=True) if precio_tag else 'no tiene'

                descripcion_tag = articulo.find('span', {'class': 'List__Description-sc-1oa0tfl-3 ljbzeb'})
                descripcion = descripcion_tag.get_text(strip=True) if descripcion_tag else 'no tiene'
                
                fecha_tag = articulo.find('time', {'class': 'List__AdMoment-sc-1oa0tfl-8 eWSYKR'})
                fecha = fecha_tag.get_text(strip=True) if fecha_tag else 'no tiene'
                
                ubicacion_tag = articulo.find('span', {'class': 'List__Location-sc-1oa0tfl-10 IKJXO'})
                ubicacion = ubicacion_tag.get_text(strip=True) if ubicacion_tag else 'no tiene'
                
                foto_indicator_tag = articulo.find('a', {'class': 'List__StyledTooltip-sc-1oa0tfl-11 ADRO'})
                foto = 'Tiene foto' if foto_indicator_tag else 'No tiene foto'

                if url == 'no tiene' or titulo == 'no tiene' or not titulo.strip():
                    logger.debug(f"Skipping item #{i} due to missing URL or Title.")
                    continue

                if 'segundos' in fecha.lower() and url != 'no tiene': 
                    desc_norm = unicodedata.normalize('NFKD', descripcion).encode('ASCII', 'ignore').decode('utf-8', 'ignore').lower()
                    tit_norm = unicodedata.normalize('NFKD', titulo).encode('ASCII', 'ignore').decode('utf-8', 'ignore').lower()
                    pk_norm = unicodedata.normalize('NFKD', palabra_clave).encode('ASCII', 'ignore').decode('utf-8', 'ignore').lower()

                    if pk_norm in desc_norm or pk_norm in tit_norm:
                        logger.debug(f"Ad matched criteria: {titulo}")
                        # Use the passed db_conn to insert the ad
                        inserted_id = db.insertar_anuncio(db_conn, url, titulo, precio, descripcion, fecha, ubicacion, foto)
                        if inserted_id: # insertar_anuncio returns lastrowid if new, None or existing ID if ignored/error
                            # Check if it's truly new by seeing if notified status would be 0 (which it is by default)
                            # This logic is now in main.py's thread. Here we just count if db.insertar_anuncio gave an ID.
                            newly_inserted_ads_count +=1 
            except Exception as e:
                logger.error(f"Error processing ad item #{i}: {e}. HTML: {str(articulo)[:200]}", exc_info=True)
                continue 
    else:
        logger.warning('No ad container found on the page.')
    logger.info(f"Processed page for '{palabra_clave}', {newly_inserted_ads_count} new ads potentially identified for DB insertion.")
    return newly_inserted_ads_count


# --- Example Usage (Illustrative - actual calls would be from main.py or similar) ---
if __name__ == '__main__':
    # This section is for testing the scraper functions directly.
    # It requires db.py to be in the same directory or python path.
    
    # Setup basic logging for testing scraper.py standalone
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_db_conn = None
    test_driver = None
    try:
        test_db_conn = db.get_db_connection()
        if not test_db_conn:
            logger.error("Failed to get DB connection for standalone test. Exiting.")
            exit()

        # Create tables needed for the test
        db.crear_tabla_anuncio(test_db_conn) # This will clear existing ads in 'anuncios' table

        test_driver = get_webdriver_instance()
        if not test_driver:
            logger.error("Failed to get WebDriver for standalone test. Exiting.")
            exit()
        
        logger.info("--- Test: Initiating search for ads (will handle pagination) ---")
        # buscar_anuncios will now loop through pages and call procesar_y_guardar_anuncios for each.
        # It now requires db_conn to be passed.
        buscar_anuncios(
            driver=test_driver,
            db_conn=test_db_conn, 
            departamento="compra-venta", 
            palabra_clave="tarjeta de video", # Using a potentially less frequent item for faster testing
            # precio_max="100", 
            # provincia="La Habana", 
            max_pages=1 # Limit number of pages for this test
        )
        logger.info("--- Test: Search process completed ---")

        # Verify ads were inserted
        ads_in_db = db.obtener_anuncios(test_db_conn)
        logger.info(f"Found {len(ads_in_db)} ads in the database after test run:")
        for ad_in_db in ads_in_db[:5]: # Print first 5
            logger.info(f"  - {ad_in_db}")

        # Example of fetching details for a *specific known* ad URL (optional)
        # if ads_in_db:
        #     known_ad_url = ads_in_db[0][1] # URL of the first ad found
        #     logger.info(f"--- Test: Obtaining contact info for a specific ad: {known_ad_url} ---")
        #     contacto, telefono, email = obtener_contacto_de_anuncio(test_driver, known_ad_url)
        #     logger.info(f"Contact - Name: {contacto}, Phone: {telefono}, Email: {email}")
        #     logger.info(f"--- Test: Obtaining images for a specific ad: {known_ad_url} ---")
        #     image_urls = obtener_imagenes_de_anuncio(test_driver, known_ad_url)
        #     logger.info(f"Images: {image_urls}")

    except Exception as e:
        logger.error(f"An error occurred during the scraper.py standalone test run: {e}", exc_info=True)
    finally:
        if test_driver: 
            close_webdriver() # Use the centralized close_webdriver
        if test_db_conn:
            db.close_db_connection(test_db_conn)
        logger.info("--- Scraper.py standalone test run finished ---")

```
