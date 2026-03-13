# -*- coding: utf-8 -*-
import os
import base64
import json
import logging
import hashlib
import re
from .ocr_helpers.cleaners import (
    normalize_phone,
    clean_text_field,
    format_structured_address,
)
from .ocr_helpers.utils import safe_float, detect_currency
from .ocr_helpers.financials import compute_financials
from .ocr_helpers.vendor_bill import create_vendor_bill
from .ocr_helpers.document_processor import process_document_data
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .azure import AzureInvoiceService

_logger = logging.getLogger(__name__)


class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    # ======================================================
    # 1) SYSTEM & STATUS (support BOTH: state + status)
    # ======================================================
    name = fields.Char(
        string="Ref",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )

    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("processing", "Processing"),
            ("done", "Done"),
            ("reviewed", "Reviewed"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )

    state = fields.Selection(related="status", string="State", readonly=True)

    progress = fields.Float(string="Progress", default=0.0, readonly=True)

    # ======================================================
    # 2) FILE HANDLING
    # ======================================================
    file_filename = fields.Char(string="File Name")
    file = fields.Binary(string="File", attachment=True, required=True)
    file_sha256 = fields.Char(string="File SHA256", readonly=True, copy=False)

    # ======================================================
    # 3) DOCUMENT TYPE & HEADER
    # ======================================================
    document_type = fields.Selection(
        [("invoice", "Invoice"), ("receipt", "Receipt")],
        string="Type",
        default="invoice",
        tracking=True,
    )

    invoice_id = fields.Char(string="Invoice / Receipt ID", tracking=True)
    invoice_date = fields.Date(string="Invoice / Receipt Date", tracking=True)
    due_date = fields.Date(string="Due Date")
    payment_terms = fields.Char(string="Payment Terms")

    reference_number = fields.Char(string="Reference No")
    confidence_score = fields.Float(string="Confidence", default=0.0)

    # ======================================================
    # 4) PARTIES
    # ======================================================
    vendor_name = fields.Char(string="Vendor Name", tracking=True)
    vendor_branch_name = fields.Char(string="Branch / Head Office", tracking=True)
    vendor_tax_id = fields.Char(string="Vendor Tax ID")
    vendor_address = fields.Text(string="Vendor Address")
    vendor_phone = fields.Char(string="Vendor Phone")
    vendor_website = fields.Char(string="Vendor Website")

    customer_name = fields.Char(string="Customer Name", tracking=True)
    customer_tax_id = fields.Char(string="Customer Tax ID")
    customer_address = fields.Text(string="Customer Address")
    customer_phone = fields.Char(string="Customer Phone")

    # Backward compatibility fields (old naming)
    doc_type = fields.Selection(related="document_type", readonly=True)
    document_number = fields.Char(related="invoice_id", readonly=True)
    document_date = fields.Date(related="invoice_date", readonly=True)

    seller_name = fields.Char(related="vendor_name", readonly=True)
    seller_tax_id = fields.Char(related="vendor_tax_id", readonly=True)
    seller_address = fields.Text(related="vendor_address", readonly=True)
    seller_phone = fields.Char(related="vendor_phone", readonly=True)
    seller_website = fields.Char(related="vendor_website", readonly=True)

    # ======================================================
    # 5) TOTALS
    # ======================================================
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )

    currency_code = fields.Char(string="Currency Code")

    subtotal_amount = fields.Monetary(string="Subtotal", currency_field="currency_id")
    discount_amount = fields.Monetary(string="Discount", currency_field="currency_id")
    vat_amount = fields.Monetary(string="VAT Amount", currency_field="currency_id")
    total_amount = fields.Monetary(string="Total", currency_field="currency_id")
    vat_base_amount = fields.Monetary(string="VAT Base", currency_field="currency_id")

    subtotal_excl_tax = fields.Monetary(
        related="subtotal_amount", currency_field="currency_id", readonly=True
    )
    total_discount = fields.Monetary(
        related="discount_amount", currency_field="currency_id", readonly=True
    )
    total_incl_tax = fields.Monetary(
        related="total_amount", currency_field="currency_id", readonly=True
    )
    # ======================================================
    # 5) TOTALS (Clear meanings)
    # ======================================================
    subtotal_excl_vat_excl_discount = fields.Monetary(
        string="Subtotal (Excl VAT, Excl Discount)",
        currency_field="currency_id",
    )

    subtotal_incl_vat_excl_discount = fields.Monetary(
        string="Subtotal (Incl VAT, Excl Discount)",
        currency_field="currency_id",
    )

    subtotal_excl_vat_incl_discount = fields.Monetary(
        string="Subtotal (Excl VAT, Incl Discount)",
        currency_field="currency_id",
    )

    total_payable = fields.Monetary(
        string="Total Payable (Incl VAT, Incl Discount)",
        currency_field="currency_id",
    )


    # ======================================================
    # 6) LOGS & OCR META
    # ======================================================
    ocr_provider = fields.Char(
        string="OCR Provider",
        default="Azure Document Intelligence",
        readonly=True,
    )
    ocr_run_at = fields.Datetime(string="OCR Run Time", readonly=True)

    upload_date = fields.Datetime(
        string="Upload Date",
        default=fields.Datetime.now,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True,
    )

    extraction_log = fields.Text(string="Extraction Log")
    extracted_text = fields.Text(string="Raw OCR Text")
    ocr_error_message = fields.Text(string="Error Message")

    # DEBUG / AUDIT LOGS
    azure_raw_response = fields.Text(string="Azure Raw Response", readonly=True)
    post_processed_response = fields.Text(string="Post Processed Data", readonly=True)

    # ======================================================
    # 7) RELATIONS
    # ======================================================
    line_ids = fields.One2many("ocr.document.line", "document_id", string="Line Items")

    # ======================================================
    # 8) ACCOUNTING LINK
    # ======================================================
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        readonly=True,
        copy=False,
    )

    # ======================================================
    # HELPERS
    # ======================================================
    # ======================================================
    # STRUCTURAL CLEANING (Non-Financial Deterministic Fixes)
    # ======================================================
    
    # ======================================================
    # CREATE / WRITE
    # ======================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("ocr.document") or _("New")
            if vals.get("file"):
                try:
                    raw = base64.b64decode(vals["file"])
                    vals["file_sha256"] = hashlib.sha256(raw).hexdigest()
                except Exception:
                    pass
        return super().create(vals_list)

    def write(self, vals):
        if "file" in vals and vals.get("file"):
            try:
                raw = base64.b64decode(vals["file"])
                vals["file_sha256"] = hashlib.sha256(raw).hexdigest()
            except Exception:
                pass
        return super().write(vals)

    # ======================================================
    # VIEW BUTTON ACTIONS
    # ======================================================
    def action_retry(self):
        for rec in self:
            rec.write({
                "status": "draft",
                "progress": 0.0,
                "ocr_error_message": False,
                "extraction_log": False,
                "extracted_text": False,
                "azure_raw_response": False,
                "post_processed_response": False,
            })

    def action_mark_reviewed(self):
        for rec in self:
            rec.write({"status": "reviewed"})

    def action_open_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            raise UserError(_("No Vendor Bill linked."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.vendor_bill_id.id,
            "view_mode": "form",
        }

    # ======================================================
    # VENDOR BILL CREATION
    # ======================================================
    def action_create_vendor_bill(self):
        return create_vendor_bill(self)
    # ======================================================
    # OCR RUN
    # ======================================================
    def action_run_ocr(self):
        self.ensure_one()

        endpoint = os.environ.get("AZURE_FORM_ENDPOINT")
        key = os.environ.get("AZURE_FORM_KEY")
        if not endpoint or not key:
            raise UserError(_("Azure Settings Missing"))
        
        self.write({"status": "processing", "progress": 10.0})
        self.env.cr.commit()

        try:
            service = AzureInvoiceService(endpoint, key)
            raw_data = service.analyze(
                base64.b64decode(self.file),
            )
            data = process_document_data(raw_data)

            # Store exact Azure output
            self.azure_raw_response = json.dumps(raw_data, indent=4, ensure_ascii=False, default=str)
            

            self.post_processed_response = json.dumps(
                data, indent=4, ensure_ascii=False, default=str
            )


            if not data:
                raise UserError(_("No data returned from Azure."))

            currency = detect_currency(self.env,data.get("currency_code"))
            fin = compute_financials(data, safe_float)

            subtotal_excl_vat_excl_discount = fin["subtotal_excl_vat_excl_discount"]
            subtotal_incl_vat_excl_discount = fin["subtotal_incl_vat_excl_discount"]
            subtotal_excl_vat_incl_discount = fin["subtotal_excl_vat_incl_discount"]
            total_payable = fin["total_payable"]

            discount_val = fin["discount_val"]
            vat_val = fin["vat_val"]

            self.extraction_log = fin["debug_text"]
            _logger.info("OCR Financial Debug:\n%s", fin["debug_text"])

            # Phones
            v_phone = normalize_phone(data.get("vendor_phone"))
            c_phone = normalize_phone(data.get("customer_phone"))


            # Structured addresses -> formatted strings
            vendor_addr = format_structured_address(data.get("vendor_address_struct"))
            customer_addr = format_structured_address(data.get("customer_address_struct"))
            vendor_addr = clean_text_field(vendor_addr)
            customer_addr = clean_text_field(customer_addr)

            self.write({
                "status": "done",
                "progress": 100.0,
                "ocr_run_at": fields.Datetime.now(),

                "extracted_text": json.dumps(data, indent=4, ensure_ascii=False, default=str),

                # header
                "invoice_id": data.get("invoice_id"),
                "invoice_date": data.get("invoice_date"),
                "due_date": data.get("due_date"),
                "payment_terms": data.get("payment_terms"),
                "reference_number": data.get("reference_number"),

                # parties
                "vendor_name": data.get("vendor_name"),
                "vendor_branch_name": data.get("vendor_branch_name"),
                "vendor_tax_id": data.get("vendor_tax_id"),
                "vendor_address": vendor_addr,
                "vendor_phone": v_phone,
                "vendor_website": data.get("vendor_website"),

                "customer_name": data.get("customer_name"),
                "customer_tax_id": data.get("customer_tax_id"),
                "customer_address": customer_addr,
                "customer_phone": c_phone,

                # totals
                                # totals (old fields kept, but made consistent)
                "currency_id": currency.id,
                "currency_code": data.get("currency_code") or currency.name,

                # Old fields (keep them meaningful)
                # subtotal_amount = base subtotal (excl VAT, excl discount)
                "subtotal_amount": subtotal_excl_vat_excl_discount,

                # vat_base_amount = same base subtotal (used as VAT base)
                "vat_base_amount": subtotal_excl_vat_excl_discount,

                "discount_amount": discount_val,
                "vat_amount": vat_val,

                # total_amount = final payable (incl VAT, incl discount effect)
                "total_amount": total_payable,

                # New clear fields
                "subtotal_excl_vat_excl_discount": subtotal_excl_vat_excl_discount,
                "subtotal_incl_vat_excl_discount": subtotal_incl_vat_excl_discount,
                "subtotal_excl_vat_incl_discount": subtotal_excl_vat_incl_discount,
                "total_payable": total_payable,


                # confidence
                "confidence_score": (safe_float(data.get("confidence_score")) or 0.0),
            })

            # Replace lines safely
            lines_cmds = [(5, 0, 0)]
            for item in (data.get("items") or []):
                lines_cmds.append((0, 0, {
                    "product_code": item.get("product_code"),
                    "description": item.get("description"),
                    "quantity": item.get("quantity", 1.0),
                    "unit_price": (item.get("unit_price") or item.get("amount") or 0.0),
                    "discount_amount": item.get("discount_amount", 0.0),
                    "tax_rate": item.get("tax_rate", 0.0),
                    "total_amount": item.get("total_amount", 0.0),
                }))
            self.write({"line_ids": lines_cmds})

        except Exception as e:
            _logger.exception("OCR Error")
            self.write({
                "status": "failed",
                "progress": 0.0,
                "ocr_error_message": str(e),
            })
