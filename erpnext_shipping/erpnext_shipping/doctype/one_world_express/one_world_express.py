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
from frappe.utils.data import get_link_to_form
from erpnext_shipping.erpnext_shipping.utils import show_error_alert

ONEWORLD_PROVIDER = "One World Express"
BASE_URL = "https://www.oneworldship.co.uk"
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 0.5
TIMEOUT = 30
CSRF_TOKEN_FORM_NAME = 'csrfmiddlewaretoken'

class OneWorldExpress(Document):
    """One World Express Settings DocType"""
    def validate(self):
        if not self.enabled:
            return

        utils = OneWorldExpressUtils(self)
        try:
            if not utils.test_connection():
                frappe.throw(_("Failed to connect to One World Express. Please check your credentials and company slug."))
        except Exception as e:
            frappe.throw(_("Error validating One World Express settings: {0}").format(str(e)))

    @frappe.whitelist()
    def test_connection(self):
        """Test One World Express connection - instance method"""
        try:
            frappe.msgprint(_("Testing connection to One World Express..."), alert=True)
            utils = OneWorldExpressUtils(self)
            if utils.test_connection():
                frappe.msgprint(_("Successfully connected to One World Express."), alert=True, indicator="green")
                return True
            else:
                frappe.msgprint(_("Failed to connect to One World Express. Please check your credentials and company slug."), alert=True, indicator="red")
                return False
        except Exception as e:
            frappe.log_error(title="One World Express Test Connection Error", message=frappe.get_traceback())
            frappe.msgprint(_(f"Error testing connection: {str(e)}"), alert=True, indicator="red")
            return False

@frappe.whitelist()
def get_one_world_utils():
    """Get One World Express utils instance"""
    settings = frappe.get_single("One World Express")
    if not settings.enabled:
        link = get_link_to_form("One World Express", "One World Express", _("One World Express Settings"))
        frappe.throw(_("Please enable One World Express Integration in {0}").format(link))
    if not settings.company_slug:
        frappe.throw(_("Company Slug is not configured in One World Express settings."))
    return OneWorldExpressUtils(settings)

@frappe.whitelist()
def test_connection(doc=None):
    """Test One World Express connection - standalone function"""
    try:
        frappe.msgprint(_("Testing connection to One World Express..."), alert=True)
        if isinstance(doc, str):
            # If doc is a JSON string (happens when called from frontend)
            doc = json.loads(doc)
            
        if doc:
            # For new or unsaved documents passed from frontend
            if isinstance(doc, dict):
                # Create a temporary settings object with the provided values
                settings = frappe._dict({
                    "username": doc.get("username"),
                    "password": doc.get("password"),
                    "company_slug": doc.get("company_slug"),
                    "tracking_url": doc.get("tracking_url", BASE_URL),
                })
                
                # Method to securely get password from dict
                settings.get_password = lambda field_name: doc.get(field_name)
            else:
                # For Document objects
                settings = doc
        else:
            # Fallback to single doc
            settings = frappe.get_single("One World Express")
            
        utils = OneWorldExpressUtils(settings)
        if utils.test_connection():
            frappe.msgprint(_("Successfully connected to One World Express."), alert=True, indicator="green")
            return True
        else:
            frappe.msgprint(_("Failed to connect to One World Express. Please check your credentials and company slug."), alert=True, indicator="red")
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
        self.password = self.settings.get_password("password")
        self.company_slug = self.settings.company_slug
        self.tracking_url = self.settings.tracking_url
        
        # URLs
        self.login_url = f"{BASE_URL}/signin"
        self.api_base_url = f"{BASE_URL}/company/{self.company_slug}"
        self.api_login_url = f"{self.api_base_url}/api/auth/login"
        self.api_shipments_url = f"{self.api_base_url}/api/shipments"
        self.api_tracking_url = f"{self.api_base_url}/api/tracking"
        self.services_page_url = f"{self.api_base_url}/shipped"
        
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
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": BASE_URL,
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        })
        return session

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with error handling and logging"""
        kwargs.setdefault('timeout', TIMEOUT)
        try:
            response = self.session.request(method=method, url=url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            error_msg = f"One World Express API HTTP error for {method} {url}: {e.response.status_code} - {e.response.text[:500]}"
            frappe.log_error(error_msg, "One World Express API HTTPError")
            raise OneWorldExpressError(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"One World Express API request failed for {method} {url}: {str(e)}"
            frappe.log_error(error_msg, "One World Express API RequestException")
            raise OneWorldExpressError(error_msg) from e

    def test_connection(self) -> bool:
        """Test connection to One World Express"""
        try:
            if self._login():
                test_url = f"{self.api_base_url}/shipped"
                response = self._make_request("GET", test_url)
                return response.status_code == 200 and "logout" in response.text.lower()
            return False
        except Exception:
            return False

    def _login(self) -> bool:
        """Login to One World Express"""
        try:
            # Get CSRF token
            response = self._make_request("GET", self.login_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': CSRF_TOKEN_FORM_NAME})
            csrf_token = csrf_token['value'] if csrf_token else None

            if not csrf_token:
                frappe.log_warning("CSRF token not found", "OneWorld Login Warning")
                return False

            # Login
            login_data = {
                "csrfmiddlewaretoken": csrf_token,
                "username": self.username,
                "password": self.password,
                "next": "",
                "g-recaptcha-response": ""  # Note: This might need to be handled differently
            }

            response = self._make_request(
                "POST",
                self.login_url,
                data=login_data,
                headers={"Referer": self.login_url}
            )

            # Check if login was successful
            return 'sessionid' in self.session.cookies and response.status_code == 200

        except Exception as e:
            frappe.log_error(f"Login failed: {str(e)}", "OneWorld Login Error")
            return False

    def get_available_services(
        self,
        delivery_address: Dict[str, Any],
        pickup_address: Dict[str, Any],
        parcels: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get available shipping services"""
        try:
            if not self._login():
                show_error_alert("authenticating with One World Express")
                return []

            response = self._make_request("GET", self.services_page_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            services = []

            for service_el in soup.select('.service-option'):
                try:
                    service_name = service_el.get('data-service-name', 'Standard Delivery')
                    price = float(service_el.get('data-price', '0.0'))
                    
                    services.append({
                        "service_provider": ONEWORLD_PROVIDER,
                        "carrier": "One World Express",
                        "service_name": service_name,
                        "total_price": price,
                        "currency": "GBP"
                    })
                except (ValueError, TypeError) as e:
                    frappe.log_error(f"Error parsing service: {str(e)}", "OneWorld Service Parsing Error")
                    continue

            return services or [{
                "service_provider": ONEWORLD_PROVIDER,
                "carrier": "One World Express",
                "service_name": "Standard Delivery",
                "total_price": 0.0,
                "currency": "GBP"
            }]

        except Exception:
            show_error_alert("fetching One World Express services")
            return []

    def create_shipment(
        self,
        shipment: str,
        delivery_address: Dict[str, Any],
        pickup_address: Dict[str, Any],
        pickup_contact: Dict[str, Any],
        shipment_parcel: Dict[str, Any],
        delivery_contact: Dict[str, Any],
        service_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create shipment in One World Express"""
        try:
            if not self._login():
                show_error_alert("authenticating with One World Express")
                return None

            shipment_data = {
                "pickup": self._format_address(pickup_address, pickup_contact),
                "delivery": self._format_address(delivery_address, delivery_contact),
                "parcel": self._format_parcel(shipment_parcel),
                "service": service_info.get("service_name", "Standard Delivery")
            }

            response = self._make_request(
                "POST",
                self.api_shipments_url,
                json=shipment_data
            )
            
            data = response.json()
            awb = data.get('awb', '')
            tracking_url = f"{self.tracking_url}?awb={awb}" if awb else self.tracking_url
            
            return {
                "service_provider": ONEWORLD_PROVIDER,
                "carrier": "One World Express",
                "carrier_service": service_info.get("service_name"),
                "shipment_id": data.get("id", ""),
                "shipment_amount": float(data.get("price", 0.0)),
                "awb_number": awb,
                "tracking_url": tracking_url
            }

        except Exception:
            show_error_alert("creating One World Express shipment")
            return None

    def get_tracking_data(self, shipment_id: str) -> Optional[Dict[str, Any]]:
        """Get tracking data from One World Express"""
        try:
            if not self._login():
                show_error_alert("authenticating with One World Express")
                return None

            response = self._make_request("GET", f"{self.api_tracking_url}/{shipment_id}")
            data = response.json()
            
            awb = data.get("awb", "")
            tracking_url = f"{self.tracking_url}?awb={awb}" if awb else self.tracking_url

            return {
                "awb_number": awb,
                "tracking_status": data.get("status", "Pending"),
                "tracking_status_info": data.get("status_description", "Shipment information received"),
                "tracking_url": tracking_url
            }

        except Exception:
            show_error_alert("fetching One World Express tracking data")
            return None

    def get_label(self, shipment_id: str) -> Optional[bytes]:
        """Get shipping label from One World Express"""
        try:
            if not self._login():
                show_error_alert("authenticating with One World Express")
                return None

            response = self._make_request(
                "GET",
                f"{self.api_shipments_url}/{shipment_id}/label",
                headers={"Accept": "application/pdf"}
            )
            return response.content

        except Exception:
            show_error_alert("fetching One World Express label")
            return None

    def _format_address(self, address: Dict[str, Any], contact: Dict[str, Any]) -> Dict[str, Any]:
        """Format address for API request"""
        return {
            "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
            "address": address.get("address_line1", ""),
            "city": address.get("city", ""),
            "postal_code": address.get("pincode", ""),
            "country": address.get("country", ""),
            "phone": contact.get("phone", ""),
            "email": contact.get("email_id", "")
        }

    def _format_parcel(self, parcel: Dict[str, Any]) -> Dict[str, Any]:
        """Format parcel data for API request"""
        return {
            "weight": float(parcel.get("weight", 0)),
            "length": float(parcel.get("length", 0)),
            "width": float(parcel.get("width", 0)),
            "height": float(parcel.get("height", 0))
        } 