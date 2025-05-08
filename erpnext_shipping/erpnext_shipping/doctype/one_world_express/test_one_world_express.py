import unittest
import json
from unittest.mock import patch, MagicMock
import frappe
from frappe.test_runner import make_test_records
from erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express import (
    OneWorldExpress,
    OneWorldExpressUtils,
    test_connection
)

class MockResponse:
    def __init__(self, json_data=None, status_code=200, text="", content=b"", headers=None):
        self.json_data = json_data or {}
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")

class TestOneWorldExpress(unittest.TestCase):
    def setUp(self):
        # Create test records
        make_test_records("One World Express")
        
        # Mock settings
        self.mock_settings = frappe.get_doc({
            "doctype": "One World Express",
            "enabled": 1,
            "username": "test_user",
            "password": "test_pass",
            "company_slug": "test-company",
            "tracking_url": "https://www.oneworldship.co.uk/track"
        })
        
        # Mock session
        self.mock_session = MagicMock()
        self.mock_session.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }

    @patch('requests.Session')
    def test_login_success(self, mock_session):
        # Mock successful login response
        mock_session.return_value = self.mock_session
        
        # Mock the initial GET request for login page
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            )
        ]
        
        # Mock successful login check
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock _make_request to return our mocked responses
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils._login()
        self.assertTrue(result)

    @patch('requests.Session')
    def test_login_failure(self, mock_session):
        # Mock failed login response
        mock_session.return_value = self.mock_session
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "error"},
                text="<html>Invalid credentials</html>",
                status_code=401
            )
        ]
        # Mock failed login check
        mock_session.return_value.cookies = {}

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock _make_request to return our mocked responses
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils._login()
        self.assertFalse(result)

    @patch('requests.Session')
    def test_get_services(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock the login response sequence
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            ),
            MockResponse(
                text="""
                <div class="service-option" data-service-name="Express Delivery" data-price="10.99"></div>
                <div class="service-option" data-service-name="Standard Delivery" data-price="5.99"></div>
                """
            )
        ]

        utils = OneWorldExpressUtils(self.mock_settings)
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        services = utils.get_available_services(
            delivery_address={"country": "UK"},
            pickup_address={"country": "UK"},
            parcels=[{"weight": 1.0}]
        )
        
        self.assertEqual(len(services), 2)
        self.assertEqual(services[0]["service_name"], "Express Delivery")
        self.assertEqual(services[0]["total_price"], 10.99)
        self.assertEqual(services[1]["service_name"], "Standard Delivery")
        self.assertEqual(services[1]["total_price"], 5.99)

    @patch('requests.Session')
    def test_create_shipment(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock the login response sequence
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            ),
            MockResponse(
                json_data={
                    "id": "12345",
                    "awb": "AWB123456",
                    "price": 10.99
                }
            )
        ]

        utils = OneWorldExpressUtils(self.mock_settings)
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils.create_shipment(
            shipment="TEST123",
            delivery_address={
                "address_line1": "123 Test St",
                "city": "Test City",
                "pincode": "12345",
                "country": "UK"
            },
            pickup_address={
                "address_line1": "456 Pickup St",
                "city": "Pickup City",
                "pincode": "67890",
                "country": "UK"
            },
            pickup_contact={
                "first_name": "John",
                "last_name": "Doe",
                "phone": "1234567890",
                "email_id": "john@test.com"
            },
            shipment_parcel={
                "weight": 1.0,
                "length": 10,
                "width": 10,
                "height": 10
            },
            delivery_contact={
                "first_name": "Jane",
                "last_name": "Smith",
                "phone": "0987654321",
                "email_id": "jane@test.com"
            },
            service_info={
                "service_name": "Express Delivery"
            }
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result["shipment_id"], "12345")
        self.assertEqual(result["awb_number"], "AWB123456")
        self.assertEqual(result["shipment_amount"], 10.99)

    @patch('requests.Session')
    def test_get_tracking_data(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock the login response sequence
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            ),
            MockResponse(
                json_data={
                    "awb": "AWB123456",
                    "status": "In Transit",
                    "status_description": "Package is in transit"
                }
            )
        ]

        utils = OneWorldExpressUtils(self.mock_settings)
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils.get_tracking_data("12345")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["awb_number"], "AWB123456")
        self.assertEqual(result["tracking_status"], "In Transit")
        self.assertEqual(result["tracking_status_info"], "Package is in transit")

    @patch('requests.Session')
    def test_get_label(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock the login response sequence
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            ),
            MockResponse(
                content=b"PDF_CONTENT",
                headers={"Content-Type": "application/pdf"}
            )
        ]

        utils = OneWorldExpressUtils(self.mock_settings)
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils.get_label("12345")
        
        self.assertIsNotNone(result)
        self.assertEqual(result, b"PDF_CONTENT")

    @patch('requests.Session')
    def test_test_connection(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock connection test response
        mock_session.return_value.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>"
            ),
            MockResponse(
                text="<html>Dashboard content with logout link</html>"
            )
        ]

        utils = OneWorldExpressUtils(self.mock_settings)
        utils._make_request = MagicMock(side_effect=mock_session.return_value.request.side_effect)
        
        result = utils.test_connection()
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main() 