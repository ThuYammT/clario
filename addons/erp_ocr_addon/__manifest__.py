# -*- coding: utf-8 -*-
{
    "name": "Clareo OCR Finance",
    "summary": "Invoice & Receipt OCR Processing (Extract → Review → Export)",
    "version": "1.0",
    "category": "Accounting",
    "author": "Your Team",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "installable": True,
    "application": True,

    "data": [
        # Security
        "security/ir.model.access.csv",

        # Sequences
        "data/ocr_sequences.xml",

        # Upload forms FIRST
        "views/ocr_invoice_form.xml",
        "views/ocr_receipt_form.xml",

        # Core views
        "views/ocr_document_tree.xml",
        "views/ocr_document_search.xml",
        "views/ocr_document_form.xml",

        # Optional dashboard
        "views/ocr_dashboard_views.xml",

        # Actions AFTER all views
        "views/ocr_actions.xml",

        # Home view AFTER actions
        "views/ocr_home_view.xml",

        # Menus LAST
        "views/menus.xml",
    ],
}