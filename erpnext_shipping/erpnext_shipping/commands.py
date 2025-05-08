import frappe
import click

@click.group()
def erpnext_shipping():
    """ERPNext Shipping CLI commands"""
    pass

@click.command('test-one-world-connection')
@click.option('--doc', help='One World Express settings as JSON or document name')
def test_one_world_connection(doc=None):
    """Test the connection to One World Express service"""
    from erpnext_shipping.erpnext_shipping.doctype.one_world_express.one_world_express import test_connection
    test_connection(doc)

commands = [
    erpnext_shipping,
    test_one_world_connection
] 