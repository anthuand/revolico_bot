from selenium import webdriver
import os
import time, requests
import unicodedata
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.select import Select

from db import crear_tabla_anuncio
from db import insertar_anuncio


def Navegador():
    options = webdriver.ChromeOptions()
    options.add_argument("start-maximized")
    options.add_argument('blink-settings=imagesEnabled=false')
    options.add_argument("--no-sandbox")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    

    driver = webdriver.Chrome(options=options, executable_path=os.environ.get("CHROMEDRIVER_PATH"))

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
    print(driver.execute_script("return navigator.userAgent;"))
    return driver


def scroll(driver):
    iter = 1
    while True:
        print('scroll')
        scrollHeight = driver.execute_script("return document.documentElement.scrollHeight")
        Height = 250 * iter
        driver.execute_script("window.scrollTo(0, " + str(Height) + ");")
        if Height > scrollHeight:
            print('End of page')
            break
        time.sleep(1)
        iter += 1


def obtener_imagenes(url):
    driver = Navegador()
    driver.get(url)
    driver.implicitly_wait(0.3)

    scroll(driver)

    # todo el html del body
    body = driver.execute_script("return document.body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")

    driver.quit()

    # obteniendo las url de las imagenes
    contenedor_imagenes = soup.find('div', {'class': 'Detail__ImagesWrapper-sc-1irc1un-8 hImDlm'})
    if contenedor_imagenes:
        imagenes = contenedor_imagenes.find_all('div')
        if imagenes:
            for imagen in imagenes:
                if imagen.find('a').get('href') is not None:
                    url = imagen.find('a').get('href')
            my_img = requests.get(url)
            print("obteniendo imagen desde : ",url)
            open('foto.jpg', 'wb').write(my_img.content)

            return url


def obtener_contacto(url):
    driver = Navegador()
    driver.get(url)
    driver.implicitly_wait(0.3)

    scroll(driver)

    # todo el html del body
    body = driver.execute_script("return document.body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")

    if soup.find('div', {'data-cy': 'adName'}) is not None:
        contacto = soup.find('div', {'data-cy': 'adName'}).get_text()
    else:
        contacto = "no tiene"
    if soup.find('a', {'data-cy': 'adPhone'}) is not None:
        telefono = soup.find('a', {'data-cy': 'adPhone'}).get_text()
    else:
        telefono = "no tiene"
    if soup.find('a', {'data-cy': 'adEmail'}) is not None:
        email = soup.find('a', {'data-cy': 'adEmail'}).get_text()
    else:
        email = "no tiene"

    driver.quit()
    return contacto, telefono, email


def obeteniendo_html(departamento, palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None,
                     fotos=None):
    driver = Navegador()

    if departamento is not None:
        url = "https://www.revolico.com/" + str(departamento) + "/search.html?q=" + str(palabra_clave)+"&order=date"
        print("Accediendo a : ",url)
    else:
        url = "https://www.revolico.com/search.html?q=" + str(palabra_clave)

    print("Departamento", departamento)
    print("palabra clave:", palabra_clave)

    driver.get(url)
    driver.maximize_window()
    driver.implicitly_wait(0.1)

    if precio_min is not None:
        cuadro_precio_min = driver.find_element_by_xpath(
            "/html/body/div/div/main/div/div/div[2]/form/div/div[1]/div[2]/input[1]")
        cuadro_precio_min.send_keys(precio_min)
        time.sleep(0.1)
    if precio_max is not None:
        cuadro_precio_max = driver.find_element_by_xpath(
            "/html/body/div/div/main/div/div/div[2]/form/div/div[1]/div[2]/input[2]")
        cuadro_precio_max.send_keys(precio_max)
        time.sleep(0.1)
    if provincia is not None:
        cuadro_provincia = Select(driver.find_element_by_xpath(
            "/html/body/div/div/main/div/div/div[2]/form/div/div[2]/div[1]/div/div[1]/select"))
        cuadro_provincia.select_by_visible_text(provincia)
        time.sleep(0.1)
    # if municipio is not None:
    #     print('poniendo municipio')
    #     cuadro_municipio = Select(driver.find_element_by_xpath(
    #         "/html/body/div/div/main/div/div/div[2]/form/div/div[2]/div[1]/div/div[2]/select"))
    #     cuadro_municipio.select_by_visible_text(municipio)
    #     time.sleep(1)
    # if fotos is not None and fotos == True:
    #     print('poniendo fotos')
    #     cuadro_fotos = driver.find_element_by_xpath(
    #         "/html/body/div/div/main/div/div/div[2]/form/div/div[2]/div[2]/label/input")
    #     cuadro_fotos.click()
    #     time.sleep(1)
    boton_buscar_secundario = driver.find_element_by_xpath(
        "/html/body/div/div/main/div/div/div[2]/form/div/div[3]/button")
    boton_buscar_secundario.click()

    scroll(driver)

    # todo el html del body
    body = driver.execute_script("return document.body")
    source = body.get_attribute('innerHTML')
    soup = BeautifulSoup(source, "lxml")

    driver.quit()
    return soup


def get_main_anuncios(departamento, palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None,
                      fotos=None):
    contenido_web = obeteniendo_html(departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos)
    # print(contenido_web)
    anuncios = contenido_web.find('ul')
    if anuncios != None:
        articulos = anuncios.find_all('li')

        try:
            crear_tabla_anuncio()
            for articulo in articulos:
                if articulo.find('a').get('href') is not None:
                    url = articulo.find('a').get('href')
                else:
                    url = 'no tiene'
                if articulo.find('span', {'data-cy': 'adTitle'}) is not None:
                    titulo = articulo.find('span', {'data-cy': 'adTitle'}).get_text()
                else:
                    titulo = 'no tiene'
                if articulo.find('span', {'data-cy': 'adPrice'}) is not None:
                    precio = articulo.find('span', {'data-cy': 'adPrice'}).get_text()
                else:
                    precio = 'no tiene'
                if articulo.find('span', {'class': 'List__Description-sc-1oa0tfl-3 ljbzeb'}) is not None:
                    descripcion = articulo.find('span', {'class': 'List__Description-sc-1oa0tfl-3 ljbzeb'}).get_text()
                else:
                    descripcion = 'no tiene'
                if articulo.find('time', {'class': 'List__AdMoment-sc-1oa0tfl-8 eWSYKR'}) is not None:
                    fecha = articulo.find('time', {'class': 'List__AdMoment-sc-1oa0tfl-8 eWSYKR'}).get_text()
                else:
                    fecha = 'no tiene'
                if articulo.find('span', {'class': 'List__Location-sc-1oa0tfl-10 IKJXO'}) is not None:
                    ubicacion = articulo.find('span', {'class': 'List__Location-sc-1oa0tfl-10 IKJXO'}).get_text()
                else:
                    ubicacion = 'no tiene'
                if articulo.find('a', {'class': 'List__StyledTooltip-sc-1oa0tfl-11 ADRO'}) is not None:
                    foto = articulo.find('a', {'class': 'List__StyledTooltip-sc-1oa0tfl-11 ADRO'}).get_text()
                else:
                    foto = 'no tiene'

                if str(fecha).find('segundos') != -1 and str(url) != 'no tiene' and (unicodedata.normalize('NFKD', descripcion).encode('ASCII', 'ignore').lower().find(palabra_clave) != -1 or unicodedata.normalize('NFKD', titulo).encode('ASCII', 'ignore').lower().find(palabra_clave) != -1 ): 
                    insertar_anuncio(url=url, 
                                     titulo=titulo, 
                                     precio=precio,
                                     descripcion=descripcion, 
                                     fecha=fecha,
                                     ubicacion=ubicacion, 
                                     foto=foto
                                     )

        except Exception as e:
            print(e)
    else:
        print('No esta devolviendo anuncios')


