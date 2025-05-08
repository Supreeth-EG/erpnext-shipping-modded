import unittest
import json
from unittest.mock import patch, MagicMock
import frappe
from frappe.test_runner import make_test_records
from erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express import (
    OneWorldExpress,
    OneWorldExpressUtils,
    test_connection,
    CSRF_TOKEN_FORM_NAME
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
        # Create a mock session
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        
        # Set up the session cookies
        mock_session_instance.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock the initial GET request for login page
        mock_session_instance.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "success"},
                text="<html>Welcome to OneWorld</html>",
                status_code=200
            )
        ]

        # Create utils instance
        utils = OneWorldExpressUtils(self.mock_settings)
        
        # Replace the session with our mock
        utils.session = mock_session_instance
        
        # Mock _make_request to use our mock session's request
        utils._make_request = MagicMock(side_effect=mock_session_instance.request)
        
        # Test login
        result = utils._login()
        self.assertTrue(result)
        
        # Verify the login process
        self.assertEqual(mock_session_instance.request.call_count, 2)
        
        # Verify first call was GET to login page
        first_call = mock_session_instance.request.call_args_list[0]
        self.assertEqual(first_call[0][0], "GET")
        self.assertEqual(first_call[0][1], utils.site_login_url)
        
        # Verify second call was POST to login API
        second_call = mock_session_instance.request.call_args_list[1]
        self.assertEqual(second_call[0][0], "POST")
        self.assertEqual(second_call[0][1], utils.api_login_url)
        self.assertIn("username", second_call[1]["data"])
        self.assertIn("password", second_call[1]["data"])
        self.assertIn(CSRF_TOKEN_FORM_NAME, second_call[1]["data"])

    @patch('requests.Session')
    def test_login_failure(self, mock_session):
        # Create a mock session
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        
        # Set up empty cookies for failed login
        mock_session_instance.cookies = {}
        
        # Mock the initial GET request for login page
        mock_session_instance.request.side_effect = [
            MockResponse(
                text="<html><form><input name='csrfmiddlewaretoken' value='test_csrf_token'></form></html>"
            ),
            MockResponse(
                json_data={"status": "error"},
                text="<html>Invalid credentials</html>",
                status_code=401
            )
        ]

        # Create utils instance
        utils = OneWorldExpressUtils(self.mock_settings)
        
        # Replace the session with our mock
        utils.session = mock_session_instance
        
        # Mock _make_request to use our mock session's request
        utils._make_request = MagicMock(side_effect=mock_session_instance.request)
        
        # Test login
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
        
        # Mock services page response
        mock_session.return_value.request.return_value = MockResponse(
            json_data={},  # Empty JSON data since we're parsing HTML
            text="""
            <div class="service-option" data-service-name="Express Delivery" data-price="10.99">
                Express Delivery
            </div>
            <div class="service-option" data-service-name="Standard Delivery" data-price="5.99">
                Standard Delivery
            </div>
            """
        )

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock successful login
        utils._login = MagicMock(return_value=True)
        
        services = utils.get_available_services(
            delivery_address={"address_line1": "123 Test St", "city": "Test City", "pincode": "12345", "country": "UK"},
            pickup_address={"address_line1": "456 Test Ave", "city": "Test City", "pincode": "67890", "country": "UK"},
            parcels=[{"weight": 1.0, "length": 10, "width": 10, "height": 10}]
        )

        self.assertEqual(len(services), 2)
        self.assertEqual(services[0]["service_name"], "Express Delivery")
        self.assertEqual(services[0]["total_price"], 10.99)

    @patch('requests.Session')
    def test_create_shipment(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock shipment creation response
        mock_session.return_value.request.return_value = MockResponse(
            json_data={
                "id": "SHIP123",
                "awb": "AWB123",
                "price": 15.99,
                "status": "created"
            }
        )

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock successful login
        utils._login = MagicMock(return_value=True)
        
        shipment = utils.create_shipment(
            shipment="TEST123",
            delivery_address={"address_line1": "123 Test St", "city": "Test City", "pincode": "12345", "country": "UK"},
            pickup_address={"address_line1": "456 Test Ave", "city": "Test City", "pincode": "67890", "country": "UK"},
            pickup_contact={"first_name": "John", "last_name": "Doe", "phone": "1234567890", "email_id": "john@test.com"},
            shipment_parcel={"weight": 1.0, "length": 10, "width": 10, "height": 10},
            delivery_contact={"first_name": "Jane", "last_name": "Smith", "phone": "0987654321", "email_id": "jane@test.com"},
            service_info={"service_name": "Express Delivery"}
        )

        self.assertEqual(shipment["shipment_id"], "SHIP123")
        self.assertEqual(shipment["awb_number"], "AWB123")
        self.assertEqual(shipment["shipment_amount"], 15.99)

    @patch('requests.Session')
    def test_get_tracking_data(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock tracking data response
        mock_session.return_value.request.return_value = MockResponse(
            json_data={
                "awb": "AWB123",
                "status": "In Transit",
                "status_description": "Package is in transit",
                "last_update": "2024-03-19T10:00:00Z"
            }
        )

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock successful login
        utils._login = MagicMock(return_value=True)
        
        tracking = utils.get_tracking_data("SHIP123")

        self.assertEqual(tracking["awb_number"], "AWB123")
        self.assertEqual(tracking["tracking_status"], "In Transit")
        self.assertEqual(tracking["tracking_status_info"], "Package is in transit")

    @patch('requests.Session')
    def test_get_label(self, mock_session):
        # Mock successful login first
        mock_session.return_value = self.mock_session
        mock_session.return_value.cookies = {
            'sessionid': 'test_session_id',
            'csrftoken': 'test_csrf_token'
        }
        
        # Mock label response
        mock_session.return_value.request.return_value = MockResponse(
            json_data={},  # Empty JSON data since we're getting PDF content
            content=b"PDF_CONTENT",
            headers={"Content-Type": "application/pdf"}
        )

        utils = OneWorldExpressUtils(self.mock_settings)
        # Mock successful login
        utils._login = MagicMock(return_value=True)
        
        label = utils.get_label("SHIP123")

        self.assertEqual(label, b"PDF_CONTENT")

    def test_test_connection(self):
        with patch('erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express.get_one_world_utils') as mock_utils:
            # Create a mock utils instance
            mock_utils_instance = MagicMock()
            mock_utils.return_value = mock_utils_instance
            
            # Mock successful login
            mock_utils_instance._login.return_value = True
            
            # Mock the test URL response
            mock_utils_instance.base_url = "https://www.oneworldship.co.uk"
            mock_utils_instance.company_slug = "test-company"
            mock_utils_instance._make_request.return_value = MockResponse(
                json_data={},
                text="<html><a href='/logout'>Logout</a></html>"
            )
            
            # Mock frappe.msgprint to prevent actual message display
            with patch('frappe.msgprint'):
                result = test_connection()
                self.assertTrue(result)

if __name__ == '__main__':
    unittest.main() 