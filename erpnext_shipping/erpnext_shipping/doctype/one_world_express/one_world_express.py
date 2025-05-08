import frappe
from frappe import _
from frappe.model.document import Document
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List, Optional, Union, Any

ONEWORLD_PROVIDER = "One World Express"
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 0.5
TIMEOUT = 30
CSRF_TOKEN_FORM_NAME = 'csrfmiddlewaretoken' # Common name for CSRF token in forms

class OneWorldExpress(Document):
    """One World Express Settings DocType"""
    pass

@frappe.whitelist()
def get_one_world_utils():
    """Get One World Express utils instance"""
    settings = frappe.get_single("One World Express")
    if not settings.enabled:
        frappe.throw(_("One World Express is not enabled in settings."))
    if not settings.company_slug:
        frappe.throw(_("Company Slug is not configured in One World Express settings."))
    return OneWorldExpressUtils(settings)

@frappe.whitelist()
def test_connection():
    """Test One World Express connection"""
    try:
        # Show notification that test is starting
        frappe.msgprint(_("Testing connection to One World Express..."), alert=True)
        
        utils = get_one_world_utils()
        if utils._login():
            # Optionally, try a simple read operation if login alone is not sufficient proof
            # For example, try to fetch a non-sensitive page like the main dashboard after login
            # Test by trying to access a page that requires login
            test_url = f"{utils.base_url}/company/{utils.company_slug}/shipped" # An example protected page
            response = utils._make_request("GET", test_url)
            if response.status_code == 200 and "logout" in response.text.lower(): # Check for a common logged-in indicator
                 frappe.msgprint(_("Successfully connected and authenticated with One World Express."), alert=True, indicator="green")
                 return True
            else:
                frappe.log_error(f"OneWorld Test Connection: Login succeeded but could not confirm access to protected page {test_url}. Status: {response.status_code}", "OneWorld Connection Test Error")
                frappe.msgprint(_("Connection test partially failed: Login successful, but could not verify access to resources. Check logs."), alert=True, indicator="orange")
                return False # Login might have appeared successful but wasn't really

        else:
            frappe.msgprint(_("Failed to connect to One World Express. Please check your credentials, company slug, and logs."), alert=True, indicator="red")
            return False
    except Exception as e:
        frappe.log_error(title="One World Express Test Connection Error", message=frappe.get_traceback())
        frappe.msgprint(_(f"Error testing connection: {str(e)}"), alert=True, indicator="red")
        return False

class OneWorldExpressError(Exception):
    """Custom exception for One World Express errors"""
    pass

class OneWorldExpressUtils:
    """One World Express Integration Utils"""
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        if settings is None:
             self.settings = frappe.get_single("One World Express")
        else:
            self.settings = settings

        self.username = self.settings.username
        self.password = self.settings.get_password("password") # Ensure password is fetched securely
        self.base_url = "https://www.oneworldship.co.uk"
        self.company_slug = self.settings.company_slug
        
        # General URLs
        self.site_login_url = f"{self.base_url}/login" # HTML Login page for initial cookie fetching
        self.tracking_url_template = self.settings.tracking_url # From settings, e.g., https://www.oneworldship.co.uk/track

        # API and Scraped Page URLs - using company slug
        self.api_base_path = f"{self.base_url}/company/{self.company_slug}"
        self.api_login_url = f"{self.api_base_path}/api/auth/login" # API endpoint for login POST
        self.api_shipments_url = f"{self.api_base_path}/api/shipments"
        self.api_tracking_url = f"{self.api_base_path}/api/tracking" 
        
        # URL for the page to be scraped for services (based on cURL referer)
        self.services_page_url = f"{self.api_base_path}/shipped" 

        self.session = self._configure_session()
        
    def _configure_session(self) -> requests.Session:
        """Configure session with retry mechanism and timeouts"""
        session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"])
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8"
        })
        return session

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with error handling and logging"""
        # Ensure default timeout if not provided
        kwargs.setdefault('timeout', TIMEOUT)
        try:
            response = self.session.request(method=method, url=url, **kwargs)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return response
        except requests.exceptions.HTTPError as e:
            error_msg = f"One World Express API HTTP error for {method} {url}: {e.response.status_code} - {e.response.text[:500]}"
            frappe.log_error(error_msg, "One World Express API HTTPError")
            raise OneWorldExpressError(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"One World Express API request failed for {method} {url}: {str(e)}"
            frappe.log_error(error_msg, "One World Express API RequestException")
            raise OneWorldExpressError(error_msg) from e

    def _login(self) -> bool:
        """Login to One World Express using form-based authentication."""
        try:
            # Step 1: GET the HTML login page to obtain CSRF token and other cookies.
            # The session object will store these cookies automatically.
            self._make_request("GET", self.site_login_url) 
            
            csrf_token = self.session.cookies.get(CSRF_TOKEN_FORM_NAME) or \
                         self.session.cookies.get('csrftoken') # Common variations
            
            if not csrf_token:
                frappe.log_warning("CSRF token not found after GET to login page.", "OneWorld Login Warning")
                # Depending on the site, login might still work without CSRF in payload if it's only in cookies

            login_payload = {
                "username": self.username,
                "password": self.password,
                "remember": "true" # Common field, adjust if different
            }
            if csrf_token:
                 login_payload[CSRF_TOKEN_FORM_NAME] = csrf_token
            
            login_headers = {
                "Referer": self.site_login_url,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            # Step 2: POST to the API login URL with credentials and CSRF token.
            response = self.session.request(
                method="POST",
                url=self.api_login_url,
                data=login_payload,
                headers=login_headers,
                timeout=TIMEOUT
            )
            response.raise_for_status() # Check for 4xx/5xx errors immediately

            # Success criteria: 
            # 1. 'sessionid' cookie is present in the session after the POST.
            # 2. Response does not indicate a login failure (e.g., by redirecting back to login or showing error messages).
            if 'sessionid' in self.session.cookies and response.status_code == 200:
                # More robust check: ensure response text doesn't contain typical login error phrases.
                response_text_lower = response.text.lower()
                login_error_phrases = [
                    "incorrect username or password", "login failed", 
                    "please enter valid credentials", "authentication failed"
                ]
                if not any(phrase in response_text_lower for phrase in login_error_phrases):
                    frappe.log_info("OneWorld Express login successful.", "OneWorld Login")
                    # Remove Authorization header if it was set by a previous token-based attempt
                    if "Authorization" in self.session.headers:
                        del self.session.headers["Authorization"]
                    return True

            log_message = f"OneWorld Login to {self.api_login_url} failed or was ambiguous. Status: {response.status_code}. \
                          'sessionid' cookie present: {'sessionid' in self.session.cookies}. \
                          Response (first 300 chars): {response.text[:300]}"
            frappe.log_error(log_message, "OneWorld Login Failure")
            return False
            
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text[:500] if hasattr(e, 'response') and e.response else str(e)
            frappe.log_error(f"One World Express login request exception: {error_detail}", "One World Express Login Error")
            return False
        except Exception as e:
            frappe.log_error(f"Unexpected error during One World Express login: {frappe.get_traceback()}", "One World Express Login Error")
            return False

    def get_available_services(
        self, 
        delivery_address: Dict[str, Any], 
        pickup_address: Dict[str, Any], 
        parcels: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get available shipping services from One World Express.
        WARNING: This method currently relies on HTML scraping, which is highly fragile 
        and prone to breaking if the website structure changes. 
        It is STRONGLY recommended to obtain a dedicated API endpoint for fetching 
        shipping rates/services from One World Express for production use.
        """
        if not self._login(): # Ensure session is authenticated
            frappe.throw(_("OneWorld Express: Authentication failed. Cannot get services."))
            return []

        try:
            # Navigate to the page from which services are scraped.
            # The user's cURL referer was '.../company/.../shipped', so we use services_page_url.
            response = self._make_request("GET", self.services_page_url)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            services: List[Dict[str, Any]] = []
            # IMPORTANT: The selector '.service-option' and data attributes are based on previous assumptions.
            # This needs to be verified against the actual HTML of self.services_page_url.
            service_elements = soup.select('.service-option') 
            
            if not service_elements:
                frappe.log_warning(
                    f"No service elements found using selector '.service-option' on {self.services_page_url}. "
                    f"The page structure might have changed or services are not listed here.",
                    "OneWorld Service Discovery"
                )

            for service_el in service_elements:
                try:
                    service_name = service_el.get('data-service-name', 'Standard Delivery')
                    total_price_str = service_el.get('data-price', '0.0')
                    total_price = float(total_price_str) if total_price_str else 0.0
                    
                    services.append({
                        "service_provider": ONEWORLD_PROVIDER,
                        "carrier": "One World Express", # Or derive if available
                        "service_name": service_name,
                        "total_price": total_price,
                        "currency": "GBP" # Or derive if available
                    })
                except (ValueError, TypeError) as e:
                    frappe.log_error(
                        f"Error parsing service data element: {str(service_el)}. Error: {str(e)}", 
                        "One World Express Service Parsing Error"
                    )
                    continue # Skip this service if parsing fails
            
            if services:
                return services
            else:
                # Fallback if no services are found or parsed successfully
                frappe.log_warning(
                    f"No services were successfully parsed from {self.services_page_url}. Providing a default fallback service.",
                    "OneWorld Service Discovery Fallback"
                )
                return [{
                    "service_provider": ONEWORLD_PROVIDER,
                    "carrier": "One World Express",
                    "service_name": "Default Service (Check Manually)",
                    "total_price": 0.0,
                    "currency": "GBP"
                }]
            
        except OneWorldExpressError as e:
             # Catch errors from _make_request or _login
            frappe.log_error(f"Failed to get One World Express services due to API/Login error: {str(e)}", "One World Express Services Error")
            raise # Re-throw to be caught by the caller or Frappe's error handling
        except Exception as e:
            frappe.log_error(f"Unexpected error getting One World Express services: {frappe.get_traceback()}", "One World Express Services Error")
            # Consider if a fallback is appropriate or if an error should be raised to the user
            frappe.throw(_(f"Failed to retrieve services from One World Express: {str(e)}"))
            return [] # Should be unreachable if frappe.throw works

    def create_shipment(
        self,
        shipment: str, # Assuming this is an identifier for ERPNext Shipment Doc
        delivery_address: Dict[str, Any],
        pickup_address: Dict[str, Any],
        pickup_contact: Dict[str, Any],
        shipment_parcel: Dict[str, Any],
        delivery_contact: Dict[str, Any],
        service_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create shipment in One World Express"""
        if not self._login():
            frappe.throw(_("OneWorld Express: Authentication failed. Cannot create shipment."))
            return None

        try:
            shipment_data = {
                "pickup": {
                    "name": f"{pickup_contact.get('first_name', '')} {pickup_contact.get('last_name', '')}".strip(),
                    "address": pickup_address.get("address_line1", ""),
                    "city": pickup_address.get("city", ""),
                    "postal_code": pickup_address.get("pincode", ""),
                    "country": pickup_address.get("country", ""),
                    "phone": pickup_contact.get("phone", ""),
                    "email": pickup_contact.get("email_id", "")
                },
                "delivery": {
                    "name": f"{delivery_contact.get('first_name', '')} {delivery_contact.get('last_name', '')}".strip(),
                    "address": delivery_address.get("address_line1", ""),
                    "city": delivery_address.get("city", ""),
                    "postal_code": delivery_address.get("pincode", ""),
                    "country": delivery_address.get("country", ""),
                    "phone": delivery_contact.get("phone", ""),
                    "email": delivery_contact.get("email_id", "")
                },
                "parcel": {
                    "weight": float(shipment_parcel.get("weight", 0)),
                    "length": float(shipment_parcel.get("length", 0)),
                    "width": float(shipment_parcel.get("width", 0)),
                    "height": float(shipment_parcel.get("height", 0))
                },
                "service": service_info.get("service_name", "Standard Delivery") # This should match a service from their system
            }

            response = self._make_request(
                "POST",
                self.api_shipments_url,
                json=shipment_data, # Assuming API expects JSON for shipment creation
                headers={"Content-Type": "application/json"} # Explicitly set Content-Type for JSON
            )
            
            shipment_response = response.json()
            awb = shipment_response.get('awb', '')
            tracking_url_filled = f"{self.tracking_url_template}?awb={awb}" if awb else self.tracking_url_template
            
            return {
                "service_provider": ONEWORLD_PROVIDER,
                "carrier": "One World Express",
                "carrier_service": service_info.get("service_name"),
                "shipment_id": shipment_response.get("id", ""), 
                "shipment_amount": float(shipment_response.get("price", 0.0)),
                "awb_number": awb,
                "tracking_url": tracking_url_filled
            }

        except OneWorldExpressError as e:
            frappe.log_error(f"Failed to create One World Express shipment due to API/Login error: {str(e)}", "One World Express Shipment Error")
            raise
        except Exception as e:
            frappe.log_error(f"Unexpected error creating One World Express shipment: {frappe.get_traceback()}", "One World Express Shipment Error")
            frappe.throw(_(f"Failed to create shipment with One World Express: {str(e)}"))
            return None

    def get_tracking_data(self, shipment_id: str) -> Optional[Dict[str, Any]]:
        """Get tracking data from One World Express"""
        if not self._login():
            frappe.throw(_("OneWorld Express: Authentication failed. Cannot get tracking data."))
            return None

        try:
            # shipment_id here is likely the ID from OneWorld, not ERPNext's Shipment Doc name.
            # This ID would have been returned when creating the shipment.
            response = self._make_request("GET", f"{self.api_tracking_url}/{shipment_id}")
            tracking_data = response.json()
            
            awb = tracking_data.get("awb", "")
            tracking_url_filled = f"{self.tracking_url_template}?awb={awb}" if awb else self.tracking_url_template

            return {
                "awb_number": awb,
                "tracking_status": tracking_data.get("status", "Pending"),
                "tracking_status_info": tracking_data.get("status_description", "Shipment information received"),
                "tracking_url": tracking_url_filled
            }

        except OneWorldExpressError as e:
            frappe.log_error(f"Failed to get One World Express tracking data due to API/Login error: {str(e)}", "One World Express Tracking Error")
            raise
        except Exception as e:
            frappe.log_error(f"Unexpected error getting One World Express tracking data for {shipment_id}: {frappe.get_traceback()}", "One World Express Tracking Error")
            frappe.throw(_(f"Failed to get tracking data from One World Express: {str(e)}"))
            return None

    def get_label(self, shipment_id: str) -> Optional[bytes]:
        """Get shipping label from One World Express"""
        if not self._login():
            frappe.throw(_("OneWorld Express: Authentication failed. Cannot get label."))
            return None

        try:
            # shipment_id here is likely the ID from OneWorld.
            response = self._make_request(
                "GET",
                f"{self.api_shipments_url}/{shipment_id}/label",
                headers={"Accept": "application/pdf"} # Request PDF content
            )
            return response.content

        except OneWorldExpressError as e:
            frappe.log_error(f"Failed to get One World Express label due to API/Login error: {str(e)}", "One World Express Label Error")
            raise
        except Exception as e:
            frappe.log_error(f"Unexpected error getting One World Express label for {shipment_id}: {frappe.get_traceback()}", "One World Express Label Error")
            frappe.throw(_(f"Failed to get label from One World Express: {str(e)}"))
            return None 