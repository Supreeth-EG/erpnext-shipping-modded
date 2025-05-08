frappe.ui.form.on('One World Express', {
    refresh: function(frm) {
        // Add test connection button
        frm.add_custom_button(__('Test Connection'), function() {
            frappe.call({
                method: 'test_connection',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __('Connection successful!'),
                            indicator: 'green'
                        });
                    } else {
                        frappe.show_alert({
                            message: __('Connection failed. Please check your credentials.'),
                            indicator: 'red'
                        });
                    }
                },
                error: function(r) {
                    frappe.show_alert({
                        message: __('Error testing connection: ') + r.message,
                        indicator: 'red'
                    });
                }
            });
        });
    },
    
    validate: function(frm) {
        // Validate form data before saving
        if (frm.doc.enabled && !frm.doc.username) {
            frappe.throw(__('Username is required when One World Express is enabled'));
        }
        if (frm.doc.enabled && !frm.doc.password) {
            frappe.throw(__('Password is required when One World Express is enabled'));
        }
        if (frm.doc.enabled && !frm.doc.company_slug) {
            frappe.throw(__('Company Slug is required when One World Express is enabled'));
        }
        if (frm.doc.enabled && !frm.doc.tracking_url) {
            frappe.throw(__('Tracking URL is required when One World Express is enabled'));
        }
    }
}); 