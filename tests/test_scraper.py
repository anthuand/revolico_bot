import unittest
from unittest.mock import patch, Mock, MagicMock
import sys
import os
from bs4 import BeautifulSoup
import requests # For requests.exceptions.RequestException

# Add the parent directory to sys.path to allow scraper module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Functions to be tested from scraper.py
from scraper import Navegador, scroll, obtener_imagenes, obtener_contacto, obeteniendo_html, get_main_anuncios

# --- Sample HTML Content for Mocks ---
SAMPLE_HTML_NO_IMAGES = """
<html><body>
    <div>No images here</div>
</body></html>
"""

SAMPLE_HTML_WITH_IMAGE = """
<html><body>
    <div class='Detail__ImagesWrapper-sc-1irc1un-8 hImDlm'>
        <div><a href='http://example.com/image.jpg'></a></div>
    </div>
</body></html>
"""

SAMPLE_HTML_WITH_RELATIVE_IMAGE = """
<html><body>
    <div class='Detail__ImagesWrapper-sc-1irc1un-8 hImDlm'>
        <div><a href='/relative_image.png'></a></div>
    </div>
</body></html>
"""

SAMPLE_HTML_NO_CONTACT = """
<html><body>
    <div>No contact info</div>
</body></html>
"""

SAMPLE_HTML_WITH_CONTACT = """
<html><body>
    <div data-cy='adName'>Test User</div>
    <a data-cy='adPhone'>123456789</a>
    <a data-cy='adEmail'>test@example.com</a>
</body></html>
"""

SAMPLE_HTML_PARTIAL_CONTACT = """
<html><body>
    <div data-cy='adName'>Another User</div>
</body></html>
"""

SAMPLE_AD_LIST_HTML = """
<ul>
    <li>
        <a href="/ad1-segundos.html"></a>
        <span data-cy="adTitle">Ad Title 1 Segundos</span>
        <span data-cy="adPrice">100 CUC</span>
        <span class="List__Description-sc-1oa0tfl-3 ljbzeb">Description for ad 1 with keyword.</span>
        <time class="List__AdMoment-sc-1oa0tfl-8 eWSYKR">hace 5 segundos</time>
        <span class="List__Location-sc-1oa0tfl-10 IKJXO">Havana</span>
        <a class="List__StyledTooltip-sc-1oa0tfl-11 ADRO">Tooltip for photo</a>
    </li>
    <li>
        <a href="/ad2-minutos.html"></a>
        <span data-cy="adTitle">Ad Title 2 Minutos</span>
        <span data-cy="adPrice">200 CUC</span>
        <span class="List__Description-sc-1oa0tfl-3 ljbzeb">Description for ad 2.</span>
        <time class="List__AdMoment-sc-1oa0tfl-8 eWSYKR">hace 5 minutos</time>
        <span class="List__Location-sc-1oa0tfl-10 IKJXO">Matanzas</span>
    </li>
    <li>
        <!-- Ad that matches keyword but is not recent enough -->
        <a href="/ad3-horas.html"></a>
        <span data-cy="adTitle">Ad Title 3 Horas Keyword</span>
        <span data-cy="adPrice">300 CUC</span>
        <span class="List__Description-sc-1oa0tfl-3 ljbzeb">Old ad with keyword.</span>
        <time class="List__AdMoment-sc-1oa0tfl-8 eWSYKR">hace 2 horas</time>
        <span class="List__Location-sc-1oa0tfl-10 IKJXO">Pinar del Rio</span>
    </li>
     <li>
        <a href="/ad4-segundos-no-keyword.html"></a>
        <span data-cy="adTitle">Ad Title 4 Segundos No Match</span>
        <span data-cy="adPrice">400 CUC</span>
        <span class="List__Description-sc-1oa0tfl-3 ljbzeb">Description for ad 4.</span>
        <time class="List__AdMoment-sc-1oa0tfl-8 eWSYKR">hace 10 segundos</time>
        <span class="List__Location-sc-1oa0tfl-10 IKJXO">Artemisa</span>
    </li>
</ul>
"""

class TestScraperOperations(unittest.TestCase):

    @patch('scraper.webdriver.Chrome')
    @patch('scraper.ChromeService')
    @patch('scraper.ChromeDriverManager')
    def test_navegador_basic_calls(self, MockChromeDriverManager, MockChromeService, MockWebDriverChrome):
        # Test that Navegador attempts to initialize Chrome and related services
        mock_driver_instance = MockWebDriverChrome.return_value
        mock_driver_manager_instance = MockChromeDriverManager.return_value
        mock_driver_manager_instance.install.return_value = "/fake/driver/path"
        mock_service_instance = MockChromeService.return_value

        driver = Navegador()

        MockChromeDriverManager.assert_called_once()
        mock_driver_manager_instance.install.assert_called_once()
        MockChromeService.assert_called_once_with(executable_path="/fake/driver/path")
        MockWebDriverChrome.assert_called_once_with(service=mock_service_instance, options=unittest.mock.ANY)
        self.assertEqual(driver, mock_driver_instance)
        # Check a few cdp/execute_script calls
        self.assertTrue(mock_driver_instance.execute_cdp_cmd.called)
        self.assertTrue(mock_driver_instance.execute_script.called)


    def _get_mock_driver(self, html_content=""):
        mock_driver = MagicMock()
        mock_body = MagicMock()
        mock_body.get_attribute.return_value = html_content
        mock_driver.execute_script.return_value = mock_body
        return mock_driver

    @patch('scraper.requests.get')
    @patch('scraper.Navegador') # Mock Navegador if called internally
    def test_obtener_imagenes_found(self, MockNavegador, mock_requests_get):
        mock_driver_internal = self._get_mock_driver(SAMPLE_HTML_WITH_IMAGE)
        MockNavegador.return_value = mock_driver_internal # If obtener_imagenes calls Navegador()

        mock_response = Mock()
        mock_response.content = b"image_bytes_here"
        mock_response.raise_for_status = Mock() # Ensure it doesn't raise
        mock_requests_get.return_value = mock_response

        # Test with driver=None (calls Navegador internally)
        img_bytes, img_url = obtener_imagenes("http://example.com/ad_with_image")
        
        MockNavegador.assert_called_once() # Called because driver was None
        mock_driver_internal.get.assert_called_with("http://example.com/ad_with_image")
        mock_requests_get.assert_called_with("http://example.com/image.jpg", timeout=10)
        self.assertEqual(img_bytes, b"image_bytes_here")
        self.assertEqual(img_url, "http://example.com/image.jpg")
        mock_driver_internal.quit.assert_called_once() # Internal driver should be quit

        # Reset mocks and test with driver provided
        MockNavegador.reset_mock()
        mock_driver_external = self._get_mock_driver(SAMPLE_HTML_WITH_RELATIVE_IMAGE)
        img_bytes_rel, img_url_rel = obtener_imagenes("http://example.com/ad_relative", driver=mock_driver_external)
        
        MockNavegador.assert_not_called() # Not called because driver was provided
        mock_driver_external.get.assert_called_with("http://example.com/ad_relative")
        mock_requests_get.assert_called_with("https://www.revolico.com/relative_image.png", timeout=10)
        self.assertEqual(img_bytes_rel, b"image_bytes_here")
        self.assertEqual(img_url_rel, "https://www.revolico.com/relative_image.png")
        mock_driver_external.quit.assert_not_called() # External driver should not be quit by function

    @patch('scraper.requests.get')
    @patch('scraper.Navegador')
    def test_obtener_imagenes_not_found(self, MockNavegador, mock_requests_get):
        mock_driver = self._get_mock_driver(SAMPLE_HTML_NO_IMAGES)
        MockNavegador.return_value = mock_driver

        img_bytes, img_url = obtener_imagenes("http://example.com/no_image_ad")
        self.assertIsNone(img_bytes)
        self.assertIsNone(img_url) # Changed from "" to None as per code logic
        mock_requests_get.assert_not_called()
        mock_driver.quit.assert_called_once()


    @patch('scraper.requests.get', side_effect=requests.exceptions.RequestException("Test network error"))
    @patch('scraper.Navegador')
    def test_obtener_imagenes_request_exception(self, MockNavegador, mock_requests_get_exception):
        mock_driver = self._get_mock_driver(SAMPLE_HTML_WITH_IMAGE) # HTML has an image URL
        MockNavegador.return_value = mock_driver

        with patch('builtins.print') as mock_print: # To check error logging
            img_bytes, img_url = obtener_imagenes("http://example.com/ad_request_fail")
        
        self.assertIsNone(img_bytes)
        self.assertIsNotNone(img_url) # URL is found, but bytes are None due to requests error
        mock_requests_get_exception.assert_called_once()
        mock_print.assert_any_call(f"Error de red al obtener imagen de http://example.com/ad_request_fail: Test network error")
        mock_driver.quit.assert_called_once()


    @patch('scraper.Navegador')
    def test_obtener_contacto_all_details(self, MockNavegador):
        mock_driver_internal = self._get_mock_driver(SAMPLE_HTML_WITH_CONTACT)
        MockNavegador.return_value = mock_driver_internal

        # Test with driver=None
        nombre, telefono, email = obtener_contacto("http://example.com/contact_ad")
        self.assertEqual(nombre, "Test User")
        self.assertEqual(telefono, "123456789")
        self.assertEqual(email, "test@example.com")
        mock_driver_internal.quit.assert_called_once()

        # Test with driver provided
        MockNavegador.reset_mock()
        mock_driver_external = self._get_mock_driver(SAMPLE_HTML_PARTIAL_CONTACT)
        nombre_p, telefono_p, email_p = obtener_contacto("http://example.com/partial_contact_ad", driver=mock_driver_external)
        self.assertEqual(nombre_p, "Another User")
        self.assertEqual(telefono_p, "no tiene") # Default value
        self.assertEqual(email_p, "no tiene")    # Default value
        mock_driver_external.quit.assert_not_called()
        MockNavegador.assert_not_called()


    @patch('scraper.Navegador')
    def test_obtener_contacto_no_details(self, MockNavegador):
        mock_driver = self._get_mock_driver(SAMPLE_HTML_NO_CONTACT)
        MockNavegador.return_value = mock_driver
        nombre, telefono, email = obtener_contacto("http://example.com/no_contact_ad")
        self.assertEqual(nombre, "no tiene")
        self.assertEqual(telefono, "no tiene")
        self.assertEqual(email, "no tiene")
        mock_driver.quit.assert_called_once()

    @patch('scraper.Navegador')
    @patch('scraper.scroll') # Mock scroll as its behavior is not directly tested here
    @patch('scraper.Select') # Mock Select for dropdowns
    def test_obeteniendo_html_url_construction_and_calls(self, MockSelect, mock_scroll, MockNavegador):
        mock_driver = self._get_mock_driver("<html></html>") # Empty HTML for this test
        MockNavegador.return_value = mock_driver
        
        # Mock find_element for the search button
        mock_search_button = Mock()
        mock_driver.find_element.return_value = mock_search_button

        # Test with departamento and keyword
        soup, driver_out = obeteniendo_html("compra-venta", "testkeyword")
        mock_driver.get.assert_called_with("https://www.revolico.com/compra-venta/search.html?q=testkeyword&order=date")
        mock_search_button.click.assert_called_once()
        mock_scroll.assert_called_with(mock_driver)
        self.assertIsNotNone(soup)
        self.assertEqual(driver_out, mock_driver) # Should return the driver it used
        # driver_out.quit() is NOT called by obeteniendo_html itself, but by its caller (get_main_anuncios)

        # Test with keyword only
        mock_search_button.reset_mock()
        mock_driver.get.reset_mock()
        soup, driver_out = obeteniendo_html(None, "anotherkeyword")
        mock_driver.get.assert_called_with("https://www.revolico.com/search.html?q=anotherkeyword")
        # ... other assertions if needed
    
    @patch('scraper.Navegador')
    def test_obeteniendo_html_exception_handling(self, MockNavegador):
        mock_driver = self._get_mock_driver()
        MockNavegador.return_value = mock_driver
        mock_driver.get.side_effect = Exception("Test Selenium Get Error")

        with patch('builtins.print') as mock_print:
            soup, driver_out = obeteniendo_html("compra-venta", "test")
        
        self.assertIsNone(soup)
        self.assertIsNone(driver_out)
        mock_driver.quit.assert_called_once() # Driver should be quit on exception
        mock_print.assert_any_call("Error en obeteniendo_html: Test Selenium Get Error")


    @patch('scraper.obeteniendo_html')
    @patch('scraper.obtener_contacto')
    @patch('scraper.obtener_imagenes')
    def test_get_main_anuncios_flow(self, mock_obt_imagenes, mock_obt_contacto, mock_obet_html):
        mock_driver_instance = MagicMock()
        mock_soup = BeautifulSoup(SAMPLE_AD_LIST_HTML, "lxml")
        mock_obet_html.return_value = (mock_soup, mock_driver_instance)

        # Define return values for mocked contact/image functions
        mock_obt_contacto.return_value = ("Mock Contact", "111", "contact@mock.com")
        mock_obt_imagenes.return_value = (b"mock_image_bytes", "http://mock.com/mock.jpg")

        keyword_to_search = "keyword"
        results = get_main_anuncios("compra-venta", keyword_to_search)

        mock_obet_html.assert_called_once_with("compra-venta", keyword_to_search, None, None, None, None, None)
        
        self.assertEqual(len(results), 1) # Only ad1 should fully match and be processed
        ad1_result = results[0]
        self.assertEqual(ad1_result['titulo'], "Ad Title 1 Segundos")
        self.assertTrue(keyword_to_search in ad1_result['descripcion'].lower())
        self.assertEqual(ad1_result['url'], "https://www.revolico.com/ad1-segundos.html")
        
        # Check that sub-functions were called for the relevant ad
        # Ad1: /ad1-segundos.html
        mock_obt_contacto.assert_called_once_with("https://www.revolico.com/ad1-segundos.html", mock_driver_instance)
        mock_obt_imagenes.assert_called_once_with("https://www.revolico.com/ad1-segundos.html", mock_driver_instance)

        self.assertEqual(ad1_result['contacto'], ("Mock Contact", "111", "contact@mock.com"))
        self.assertEqual(ad1_result['imagen'], (b"mock_image_bytes", "http://mock.com/mock.jpg"))
        
        mock_driver_instance.quit.assert_called_once() # Ensure driver is quit

    @patch('scraper.obeteniendo_html', return_value=(None, None)) # Simulate obeteniendo_html failure
    def test_get_main_anuncios_obeteniendo_html_fails(self, mock_obet_html_failure):
        results = get_main_anuncios("compra-venta", "test")
        self.assertEqual(len(results), 0) # Should return empty list
        # mock_obet_html_failure's internal driver quit is tested in its own test
        # No driver instance is passed to get_main_anuncios to quit in this case.

    @patch('scraper.obeteniendo_html')
    def test_get_main_anuncios_no_ads_on_page(self, mock_obet_html_no_ul):
        mock_driver_instance = MagicMock()
        empty_soup = BeautifulSoup("<html><body>No ul tag</body></html>", "lxml")
        mock_obet_html_no_ul.return_value = (empty_soup, mock_driver_instance)

        results = get_main_anuncios("compra-venta", "test")
        self.assertEqual(len(results), 0)
        mock_driver_instance.quit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
