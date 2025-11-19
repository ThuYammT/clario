# -*- coding: utf-8 -*-
{
    "name": "ERP OCR Addon",
    "summary": "Upload invoices/receipts → OCR extraction → auto-fill Accounting & Expenses.",
    "version": "1.0.0",
    "category": "Accounting",
    "author": "Your Name",
    "website": "https://www.example.com",
    "license": "LGPL-3",

    # Required modules for your SP2
    "depends": [
        "base",
        "account",        # for vendor bills
        "hr_expense"      # for employee receipts
    ],

    # No XML yet — we will add later
    "data": [],

    "installable": True,
    "application": True,
}
