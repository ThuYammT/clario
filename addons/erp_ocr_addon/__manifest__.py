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
        "security/ir.model.access.csv",

        "data/ocr_sequences.xml",

        # ---- VIEWS ----
        "views/ocr_actions.xml",          # MUST load first
        "views/menus.xml",                # MUST load after actions
        "views/ocr_invoice_form.xml",
        "views/ocr_receipt_form.xml",
        "views/ocr_preview_wizard.xml",
        "views/ocr_document_tree.xml",
        "views/ocr_document_search.xml",
        "views/ocr_dashboard_views.xml",
    ],

    "installable": True,
    "application": True,
}
