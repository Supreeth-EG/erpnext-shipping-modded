import frappe
from frappe import _
from frappe.utils import cint

@frappe.whitelist()
def test_one_world_connection(doc=None):
    """Test the connection to One World Express service"""
    try:
        from erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express import test_connection
        return test_connection(doc)
    except Exception as e:
        frappe.log_error(title="One World Express Connection Test Error", message=frappe.get_traceback())
        frappe.throw(_("Failed to test connection: {0}").format(str(e))) 