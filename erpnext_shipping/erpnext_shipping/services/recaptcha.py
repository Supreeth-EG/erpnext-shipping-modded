import frappe
from frappe import _
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
from typing import Optional, Dict

class RecaptchaSolver:
    """reCAPTCHA solving service using headless Selenium"""
    
    def __init__(self, username: str = None, password: str = None, chrome_driver_path: str = None):
        self.username = username
        self.password = password
        self.chrome_driver_path = chrome_driver_path
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--window-size=1920,1080')
        self.chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36')
        
        # Add undetected-chromedriver options
        self.chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        self.chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        self.chrome_options.add_experimental_option('useAutomationExtension', False)

    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome driver"""
        if self.chrome_driver_path:
            driver = webdriver.Chrome(executable_path=self.chrome_driver_path, options=self.chrome_options)
        else:
            driver = webdriver.Chrome(options=self.chrome_options)
            
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def solve(self) -> Optional[Dict]:
        """Solve reCAPTCHA challenge and get session cookie"""
        driver = None
        try:
            driver = self._create_driver()
            
            # Navigate to the login page
            driver.get("https://www.oneworldship.co.uk/signin")
            
            # Wait for the page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            
            # Fill in login form
            driver.find_element(By.NAME, "username").send_keys(self.username)
            driver.find_element(By.NAME, "password").send_keys(self.password)
            
            # Check if reCAPTCHA is present
            recaptcha_frame = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
            if recaptcha_frame:
                # Switch to reCAPTCHA frame
                driver.switch_to.frame(recaptcha_frame[0])
                
                # Wait for reCAPTCHA checkbox
                checkbox = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".recaptcha-checkbox-border"))
                )
                
                # Click the checkbox
                checkbox.click()
                
                # Wait for reCAPTCHA to be solved
                time.sleep(5)  # Give some time for the challenge to appear
                
                # Switch back to main content
                driver.switch_to.default_content()
            
            # Submit the form
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            
            # Wait for successful login
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='logout']"))
            )
            
            # Get all cookies
            cookies = driver.get_cookies()
            return {cookie['name']: cookie['value'] for cookie in cookies}
            
        except TimeoutException:
            frappe.log_error("Timeout waiting for page elements", "Selenium Error")
            return None
        except Exception as e:
            frappe.log_error(f"Error solving reCAPTCHA: {str(e)}", "Selenium Error")
            return None
        finally:
            if driver:
                driver.quit()

@frappe.whitelist()
def solve_recaptcha() -> Dict:
    """Whitelisted method to solve reCAPTCHA"""
    settings = frappe.get_single("One World Express")
    solver = RecaptchaSolver(
        username=settings.username,
        password=settings.get_password("password"),
        chrome_driver_path=settings.chrome_driver_path
    )
    solution = solver.solve()
    
    if not solution:
        frappe.throw(_("Failed to solve reCAPTCHA challenge"))
        
    return solution 