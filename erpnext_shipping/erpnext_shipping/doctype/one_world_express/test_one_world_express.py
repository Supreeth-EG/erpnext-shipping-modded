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

    @patch('erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express.requests.Session')
    def test_login_success(self, MockRequestsSessionClass):
        # This is the mock instance that requests.Session() will return
        session_mock_instance = MagicMock(name="PatchedSessionInstance")
        MockRequestsSessionClass.return_value = session_mock_instance

        # Pre-populate cookies on the mock session instance
        # These are checked by the _login method
        session_mock_instance.cookies = {
            'sessionid': 'test_session_id_pre_set', # For the final success check in _login
            'csrftoken': 'test_csrf_token_for_payload' # For csrf_token lookup
        }
        
        # Define the sequence of responses for calls to session_mock_instance.request()
        # First call: GET to site_login_url (via _make_request)
        # Second call: POST to api_login_url (direct self.session.request call in _login)
        session_mock_instance.request.side_effect = [
            MockResponse( # For the GET request
                text="<html><form><input name='csrfmiddlewaretoken' value='csrf_from_html_if_needed'></form></html>",
                status_code=200
            ),
            MockResponse( # For the POST request
                text="<html>Welcome to OneWorld</html>", # No error phrases
                status_code=200, # Critical for success check
                # This response implies sessionid is now valid.
                # Our pre-set session_mock_instance.cookies['sessionid'] covers this.
            )
        ]
        
        # Instantiate OneWorldExpressUtils. Its _configure_session method will now use the patched
        # requests.Session, so utils.session will be session_mock_instance.
        utils = OneWorldExpressUtils(self.mock_settings)

        # Verify that utils.session is indeed our mocked instance
        self.assertIs(utils.session, session_mock_instance, "utils.session should be the mocked session instance")

        # Call the _login method
        result = utils._login()
        
        # Assert that login was successful
        self.assertTrue(result, f"Login should be successful. _login returned {result}")

        # Verify that session_mock_instance.request was called twice
        self.assertEqual(session_mock_instance.request.call_count, 2, "session.request should be called twice")
        
        # Verify details of the GET call (first call)
        get_call = session_mock_instance.request.call_args_list[0]
        self.assertEqual(get_call.args[0], "GET") # Method
        self.assertEqual(get_call.args[1], utils.site_login_url) # URL

        # Verify details of the POST call (second call)
        post_call = session_mock_instance.request.call_args_list[1]
        self.assertEqual(post_call.args[0], "POST") # Method
        self.assertEqual(post_call.args[1], utils.api_login_url) # URL
        
        # Verify payload of the POST call
        posted_data = post_call.kwargs['data']
        self.assertEqual(posted_data['username'], self.mock_settings.username)
        self.assertEqual(posted_data['password'], self.mock_settings.password) # Assuming get_password was mocked or returns plain
        self.assertEqual(posted_data[CSRF_TOKEN_FORM_NAME], 'test_csrf_token_for_payload')

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