# -*- coding: utf-8 -*-
import base64
import os

from odoo import models, fields, _
from odoo.exceptions import UserError

from .azure_invoice import AzureInvoiceService


class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document"
    _order = "create_date desc"

    # BASIC
    name = fields.Char(required=True)
    file = fields.Binary(required=True, attachment=True)
    doc_type = fields.Selection(
        [("invoice", "Invoice"), ("receipt", "Receipt")],
        default="invoice",
        required=True,
    )
    upload_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    status = fields.Selection(
        [
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("error", "Error"),
        ],
        default="uploaded",
    )
    progress = fields.Integer(default=0)

    # HEADER / PARTIES
    customer_name = fields.Char()
    vendor_name = fields.Char()
    tax_id = fields.Char()
    vendor_address = fields.Text(string="Vendor Address")
    vendor_phone = fields.Char(string="Vendor Phone")

    # DOCUMENT INFO
    invoice_date = fields.Date()
    receipt_date = fields.Date()
    receipt_number = fields.Char()
    reference_number = fields.Char()

    # AMOUNTS
    subtotal_amount = fields.Float()
    discount_amount = fields.Float()
    vat_percent = fields.Float()
    vat_amount = fields.Float()
    total_amount = fields.Float()

    # OCR META
    extracted_text = fields.Text(readonly=True)
    confidence_score = fields.Float(readonly=True)
    extraction_log = fields.Text(readonly=True)

    # ITEMS
    line_ids = fields.One2many("ocr.document.line", "document_id")

    # ACTIONS
    def action_run_ocr(self):
        for doc in self:
            if not doc.file:
                raise UserError(_("Please upload a document first."))

            doc.write({"status": "processing", "progress": 20})

            try:
                endpoint = os.getenv("AZURE_FORM_ENDPOINT")
                key = os.getenv("AZURE_FORM_KEY")

                if not endpoint or not key:
                    raise UserError(_("Azure OCR credentials not configured"))

                service = AzureInvoiceService(endpoint, key)

                file_bytes = base64.b64decode(doc.file)
                parsed = service.analyze(file_bytes)

                # Clear old lines
                doc.line_ids.unlink()

                # Create lines
                for item in parsed.get("items", []):
                    self.env["ocr.document.line"].create({
                        "document_id": doc.id,
                        "item_number": item.get("item_number"),
                        "item_name": item.get("item_name"),
                        "description": item.get("description"),
                        "quantity": item.get("quantity", 1),
                        "unit_price": item.get("unit_price", 0.0),
                    })

                doc.write({
                    "status": "completed",
                    "progress": 100,
                    "vendor_name": parsed.get("vendor_name"),
                    "customer_name": parsed.get("customer_name"),
                    "tax_id": parsed.get("tax_id"),
                    "vendor_address": parsed.get("vendor_address"),
                    "vendor_phone": parsed.get("vendor_phone"),
                    "invoice_date": parsed.get("invoice_date"),
                    "receipt_number": parsed.get("receipt_number"),
                    "subtotal_amount": parsed.get("subtotal_amount"),
                    "discount_amount": parsed.get("discount_amount"),
                    "vat_percent": parsed.get("vat_percent"),
                    "vat_amount": parsed.get("vat_amount"),
                    "total_amount": parsed.get("total_amount"),
                    "confidence_score": parsed.get("confidence_score"),
                    "extraction_log": parsed.get("extraction_log"),
                    "extracted_text": parsed.get("raw_text"),
                })

            except Exception as e:
                doc.write({
                    "status": "error",
                    "progress": 100,
                    "confidence_score": 0.0,
                    "extraction_log": str(e),
                })

        return True
