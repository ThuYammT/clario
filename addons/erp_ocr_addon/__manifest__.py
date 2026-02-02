{
    "name": "Clario OCR (Enterprise)",
    "version": "1.0.0",
    "category": "Accounting",
    "summary": "Enterprise OCR for Invoices & Receipts",
    
    # ---------------------------------------------------------
    # FIXED: Added 'mail' so Odoo knows to load the chatter
    # ---------------------------------------------------------
    "depends": ["base", "web", "mail", "account"],

    "data": [
        "security/ir.model.access.csv",
        "views/actions.xml",
        "views/menus.xml",
        "views/dashboard.xml",
        "views/form.xml",
        "views/tree.xml",
        "views/search.xml",
        "views/invoice.xml",
        "views/receipt.xml",
    ],
    "application": True,
    "installable": True,
}