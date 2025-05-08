frappe.ui.form.on('One World Express', {
    refresh: function(frm) {
        // Add custom buttons or actions here if needed
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