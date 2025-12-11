# -*- coding: utf-8 -*-
{
    "name": "ERP OCR Addon",
    "summary": "Upload invoices/receipts → OCR extraction → auto-fill Accounting & Expenses.",
    "version": "1.0.4",
    "category": "Tools",
    "author": "Your Name",
    "website": "https://www.example.com",
    "license": "LGPL-3",

    "depends": [
        "base",
        "account",
        "hr_expense"
    ],

    "data": [
        # 1) Security
        "security/ir.model.access.csv",

        # 2) Sequences
        "data/ocr_sequences.xml",

        # 3) Actions and views
        "views/ocr_actions.xml",
        "views/ocr_home_view.xml",

        # Main document views (tree + search + form)
        "views/ocr_document_tree.xml",
        "views/ocr_document_search.xml",
        "views/ocr_document_form.xml",

        # Dashboard
        "views/ocr_dashboard_views.xml",

        # (Optional) Wizard XML if you still use it and it's valid
        # "wizard/ocr_preview_wizard.xml",

        # Menus (last)
        "views/menus.xml",
    ],

    "installable": True,
    "application": True,
}
