from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import time, requests
# import unicodedata # Not used
from bs4 import BeautifulSoup
from selenium.webdriver.support.select import Select

# Removed: from db import crear_tabla_anuncio
# Removed: from db import insertar_anuncio


def Navegador():
    options = webdriver.ChromeOptions()
    options.add_argument("start-maximized")
    options.add_argument('blink-settings=imagesEnabled=false')
    options.add_argument("--no-sandbox")
    options.add_argument("--headless") # Recommended for servers
    options.add_argument("--disable-gpu") # Recommended for servers
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = ChromeService(executable_path=ChromeDriverManager().install())
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


def scroll(driver):
    iter = 1
    while True:
        scrollHeight = driver.execute_script("return document.documentElement.scrollHeight")
        Height = 250 * iter
        driver.execute_script("window.scrollTo(0, " + str(Height) + ");")
        time.sleep(0.5) 
        if Height > scrollHeight:
            break
        iter += 1


def obtener_imagenes(url, driver=None):
    created_driver_locally = False
    if driver is None:
        driver = Navegador()
        created_driver_locally = True
    
    image_url_found = None
    image_bytes = None
    try:
        driver.get(url)
        body = driver.execute_script("return document.body")
        source = body.get_attribute('innerHTML')
        soup = BeautifulSoup(source, "lxml")

        contenedor_imagenes = soup.find('div', {'class': 'Detail__ImagesWrapper-sc-1irc1un-8 hImDlm'})
        if contenedor_imagenes:
            imagenes = contenedor_imagenes.find_all('div')
            if imagenes:
                for imagen_container in imagenes:
                    link_tag = imagen_container.find('a')
                    if link_tag and link_tag.get('href') and (link_tag.get('href').endswith('.jpg') or link_tag.get('href').endswith('.png')):
                        image_url_found = link_tag.get('href')
                        break 
                if not image_url_found and imagenes[0].find('a'):
                     image_url_found = imagenes[0].find('a').get('href')

        if image_url_found:
            if image_url_found.startswith('/'):
                base_url = "https://www.revolico.com" 
                image_url_found = base_url + image_url_found
            
            print("Obteniendo imagen desde : ", image_url_found)
            my_img_response = requests.get(image_url_found, timeout=10)
            my_img_response.raise_for_status() # Raise an exception for bad status codes
            image_bytes = my_img_response.content
            # Removed: open('foto.jpg', 'wb').write(my_img.content)
            return image_bytes, image_url_found

    except requests.exceptions.RequestException as e:
        print(f"Error de red al obtener imagen de {url}: {e}")
    except Exception as e:
        print(f"Error en obtener_imagenes para {url}: {e}")
    finally:
        if created_driver_locally and driver:
            driver.quit()
    return image_bytes, image_url_found # Returns (None, None) if error or no image


def obtener_contacto(url, driver=None):
    created_driver_locally = False
    if driver is None:
        driver = Navegador()
        created_driver_locally = True

    contacto, telefono, email = "no tiene", "no tiene", "no tiene"
    try:
        driver.get(url)
        body = driver.execute_script("return document.body")
        source = body.get_attribute('innerHTML')
        soup = BeautifulSoup(source, "lxml")

        if soup.find('div', {'data-cy': 'adName'}) is not None:
            contacto = soup.find('div', {'data-cy': 'adName'}).get_text(strip=True)
        if soup.find('a', {'data-cy': 'adPhone'}) is not None:
            telefono = soup.find('a', {'data-cy': 'adPhone'}).get_text(strip=True)
        if soup.find('a', {'data-cy': 'adEmail'}) is not None:
            email = soup.find('a', {'data-cy': 'adEmail'}).get_text(strip=True)
    
    except Exception as e:
        print(f"Error en obtener_contacto para {url}: {e}")
    finally:
        if created_driver_locally and driver:
            driver.quit()
    return contacto, telefono, email


def obeteniendo_html(departamento, palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None,
                     fotos=None):
    driver = Navegador()
    try:
        if departamento is not None:
            url = "https://www.revolico.com/" + str(departamento) + "/search.html?q=" + str(palabra_clave)+"&order=date"
            print("Accediendo a : ",url)
        else:
            url = "https://www.revolico.com/search.html?q=" + str(palabra_clave)
        
        driver.get(url)

        if precio_min is not None:
            cuadro_precio_min = driver.find_element("xpath", "/html/body/div/div/main/div/div/div[2]/form/div/div[1]/div[2]/input[1]")
            cuadro_precio_min.send_keys(precio_min)
            time.sleep(0.1)
        if precio_max is not None:
            cuadro_precio_max = driver.find_element("xpath", "/html/body/div/div/main/div/div/div[2]/form/div/div[1]/div[2]/input[2]")
            cuadro_precio_max.send_keys(precio_max)
            time.sleep(0.1)
        if provincia is not None:
            cuadro_provincia = Select(driver.find_element("xpath", "/html/body/div/div/main/div/div/div[2]/form/div/div[2]/div[1]/div/div[1]/select"))
            cuadro_provincia.select_by_visible_text(provincia)
            time.sleep(0.1)
        
        boton_buscar_secundario = driver.find_element("xpath", "/html/body/div/div/main/div/div/div[2]/form/div/div[3]/button")
        boton_buscar_secundario.click()
        time.sleep(0.5) 

        scroll(driver)
        body = driver.execute_script("return document.body")
        source = body.get_attribute('innerHTML')
        soup = BeautifulSoup(source, "lxml")
        
        return soup, driver
    except Exception as e:
        print(f"Error en obeteniendo_html: {e}")
        if driver:
            driver.quit()
        return None, None


def get_main_anuncios(departamento, palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None,
                      fotos=None):
    soup, driver_instance = obeteniendo_html(departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos)
    
    collected_ads = []

    if soup is None or driver_instance is None:
        print("No se pudo obtener el HTML principal o el driver. Terminando.")
        return collected_ads # Return empty list

    try:
        anuncios_ul = soup.find('ul')
        if anuncios_ul is not None:
            articulos = anuncios_ul.find_all('li')
            # Removed: crear_tabla_anuncio() 

            for articulo in articulos:
                url_anuncio = 'no tiene'
                if articulo.find('a') and articulo.find('a').get('href') is not None:
                    url_anuncio_rel = articulo.find('a').get('href')
                    if url_anuncio_rel.startswith('/'):
                        url_anuncio = "https://www.revolico.com" + url_anuncio_rel
                    else:
                        url_anuncio = url_anuncio_rel # Assume it's already absolute if not starting with /
                
                fecha_text = 'no tiene'
                if articulo.find('time', {'class': 'List__AdMoment-sc-1oa0tfl-8 eWSYKR'}) is not None:
                    fecha_text = articulo.find('time', {'class': 'List__AdMoment-sc-1oa0tfl-8 eWSYKR'}).get_text(strip=True)
                
                # Filter by "segundos" and ensure URL is present
                if 'segundos' in fecha_text and url_anuncio != 'no tiene':
                    titulo = 'no tiene'
                    if articulo.find('span', {'data-cy': 'adTitle'}) is not None:
                        titulo = articulo.find('span', {'data-cy': 'adTitle'}).get_text(strip=True)
                    
                    precio = 'no tiene'
                    if articulo.find('span', {'data-cy': 'adPrice'}) is not None:
                        precio = articulo.find('span', {'data-cy': 'adPrice'}).get_text(strip=True)
                    
                    descripcion = 'no tiene'
                    if articulo.find('span', {'class': 'List__Description-sc-1oa0tfl-3 ljbzeb'}) is not None:
                        descripcion = articulo.find('span', {'class': 'List__Description-sc-1oa0tfl-3 ljbzeb'}).get_text(strip=True)
                                   
                    ubicacion = 'no tiene'
                    if articulo.find('span', {'class': 'List__Location-sc-1oa0tfl-10 IKJXO'}) is not None:
                        ubicacion = articulo.find('span', {'class': 'List__Location-sc-1oa0tfl-10 IKJXO'}).get_text(strip=True)
                    
                    # Keyword matching (simplified, consider more robust matching if needed)
                    descrip_normalize = descripcion.lower()
                    titulo_normalize = titulo.lower()
                    palabra_clave_normalize = palabra_clave.lower() if palabra_clave else ""
                    
                    if palabra_clave_normalize in descrip_normalize or palabra_clave_normalize in titulo_normalize:
                        print(f"Anuncio relevante encontrado: {titulo}")

                        # Call obtener_contacto and obtener_imagenes using the shared driver_instance
                        contacto_info = obtener_contacto(url_anuncio, driver_instance)
                        image_bytes, image_url = obtener_imagenes(url_anuncio, driver_instance)

                        ad_data = {
                            'url': url_anuncio,
                            'titulo': titulo,
                            'precio': precio,
                            'descripcion': descripcion,
                            'fecha': fecha_text, # Using the text from the list item
                            'ubicacion': ubicacion,
                            'contacto': contacto_info, # Tuple: (nombre, telefono, email)
                            'imagen': (image_bytes, image_url) # Tuple: (bytes, url)
                        }
                        collected_ads.append(ad_data)
                        # Removed: insertar_anuncio(...) call
        else:
            print('No se encontraron anuncios (ul tag missing).')
    
    except Exception as e:
        print(f"Error en get_main_anuncios: {e}")
    finally:
        if driver_instance:
            driver_instance.quit() 
    
    return collected_ads
