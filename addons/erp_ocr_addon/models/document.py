# -*- coding: utf-8 -*-
import os
import base64
import json
import logging
import hashlib
from datetime import datetime

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
    # 1. SYSTEM & STATUS
    # ======================================================
    name = fields.Char(
        string="Ref",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )

    state = fields.Selection(
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

    progress = fields.Float(string="Progress", default=0.0, readonly=True)

    # ======================================================
    # 2. FILE HANDLING
    # ======================================================
    file_filename = fields.Char(string="File Name")
    file = fields.Binary(string="File", attachment=True, required=True)
    file_sha256 = fields.Char(string="File SHA256", readonly=True, copy=False)

    # ======================================================
    # 3. HEADER METADATA
    # ======================================================
    doc_type = fields.Selection(
        [("invoice", "Invoice"), ("receipt", "Receipt")],
        string="Type",
        default="invoice",
    )

    document_number = fields.Char(string="Doc No")
    document_date = fields.Date(string="Doc Date")
    confidence_score = fields.Float(string="Confidence", default=0.0)

    # ======================================================
    # 4. PARTIES
    # ======================================================
    seller_name = fields.Char(string="Seller Name", tracking=True)
    seller_tax_id = fields.Char(string="Seller Tax ID")
    seller_address = fields.Text(string="Seller Address")
    seller_phone = fields.Char(string="Seller Phone")
    seller_website = fields.Char(string="Seller Website")

    customer_name = fields.Char(string="Customer Name")
    customer_tax_id = fields.Char(string="Customer Tax ID")
    customer_address = fields.Text(string="Customer Address")
    customer_phone = fields.Char(string="Customer Phone")

    # ======================================================
    # 5. DOCUMENT INFO
    # ======================================================
    due_date = fields.Date(string="Due Date")
    payment_terms = fields.Char(string="Payment Terms")
    reference_number = fields.Char(string="Reference No")
    payment_reference = fields.Char(string="Payment Reference")
    notes = fields.Text(string="Notes")

    currency = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )

    # ======================================================
    # 6. TOTALS
    # ======================================================
    subtotal_excl_tax = fields.Float(string="Subtotal (Excl. Tax)")
    total_discount = fields.Float(string="Total Discount")
    vat_rate = fields.Float(string="VAT Rate (%)")
    vat_amount = fields.Float(string="VAT Amount")
    total_incl_tax = fields.Float(string="Total (Incl. Tax)")
    rounding_adjustment = fields.Float(string="Rounding Adjustment")
    amount_in_words = fields.Char(string="Amount in Words")

    # ======================================================
    # 7. LOGS & META
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

    # ======================================================
    # 8. RELATIONS
    # ======================================================
    line_ids = fields.One2many(
        "ocr.document.line",
        "document_id",
        string="Line Items",
    )

    # ======================================================
    # 9. ACCOUNTING LINK
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
    def _normalize_phone(self, phone):
        """
        Normalize phone numbers to reduce duplicates and improve partner matching.
        Keeps + sign if present; removes spaces, hyphens, parentheses.
        """
        if not phone:
            return phone
        phone = str(phone).strip()
        # Remove common separators
        for ch in [" ", "-", "(", ")", ".", "\t", "\n", "\r"]:
            phone = phone.replace(ch, "")
        return phone

    def _safe_float(self, v):
        try:
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    # ======================================================
    # CREATE / WRITE
    # ======================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("ocr.document") or _("New")
                )
            if vals.get("file"):
                try:
                    raw = base64.b64decode(vals["file"])
                    vals["file_sha256"] = hashlib.sha256(raw).hexdigest()
                except Exception:
                    pass
        return super().create(vals_list)

    def write(self, vals):
        if "file" in vals:
            try:
                raw = base64.b64decode(vals["file"])
                vals["file_sha256"] = hashlib.sha256(raw).hexdigest()
            except Exception:
                pass
        return super().write(vals)

    # ======================================================
    # ACTIONS
    # ======================================================
    def action_retry(self):
        self.write(
            {
                "state": "draft",
                "ocr_error_message": False,
                "progress": 0.0,
                "extraction_log": False,
                "extracted_text": False,
            }
        )

    def action_mark_reviewed(self):
        self.write({"state": "reviewed"})

    def action_open_vendor_bill(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.vendor_bill_id.id,
            "view_mode": "form",
        }

    # ======================================================
    # VENDOR BILL CREATION
    # ======================================================
    def _find_or_create_vendor_partner(self):
        self.ensure_one()

        if not self.seller_name:
            raise UserError(_("Seller information is missing."))

        seller_vat = (self.seller_tax_id or "").strip() or False
        seller_phone = self._normalize_phone(self.seller_phone)

        # Prefer VAT match (best unique identifier), fallback to name
        domain = [("supplier_rank", ">", 0)]
        if seller_vat:
            domain = [("vat", "=", seller_vat)] + domain
        else:
            domain = [("name", "=", self.seller_name)] + domain

        partner = self.env["res.partner"].search(domain, limit=1)

        if not partner:
            partner = self.env["res.partner"].create(
                {
                    "name": self.seller_name,
                    "vat": seller_vat,
                    "phone": seller_phone,
                    "website": self.seller_website,
                    "supplier_rank": 1,
                }
            )
        else:
            # Light enrichment (don’t overwrite good data)
            vals = {}
            if seller_vat and not partner.vat:
                vals["vat"] = seller_vat
            if seller_phone and not partner.phone:
                vals["phone"] = seller_phone
            if self.seller_website and not partner.website:
                vals["website"] = self.seller_website
            if vals:
                partner.write(vals)

        return partner

    def action_create_vendor_bill(self):
        self.ensure_one()

        if self.vendor_bill_id:
            raise UserError(_("Vendor Bill already created."))

        partner = self._find_or_create_vendor_partner()

        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append(
                (
                    0,
                    0,
                    {
                        "name": line.description,
                        "quantity": line.quantity,
                        "price_unit": line.unit_price,
                    },
                )
            )

        if not invoice_lines:
            raise UserError(_("No line items found."))

        bill_vals = {
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": self.document_date,
            "invoice_origin": self.name,
            "invoice_line_ids": invoice_lines,
        }

        bill = self.env["account.move"].create(bill_vals)
        self.vendor_bill_id = bill.id

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
        }

    # ======================================================
    # OCR LOGIC
    # ======================================================
    def _detect_currency(self, code_from_azure):
        if code_from_azure:
            cur = self.env["res.currency"].search(
                [("name", "=", code_from_azure)], limit=1
            )
            if cur:
                return cur.id
        thb = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "THB")], limit=1
        )
        return thb.id if thb else self.env.company.currency_id.id

    def action_run_ocr(self):
        self.ensure_one()

        endpoint = os.environ.get("AZURE_FORM_ENDPOINT")
        key = os.environ.get("AZURE_FORM_KEY")
        if not endpoint or not key:
            raise UserError(_("Azure Settings Missing"))

        self.write({"state": "processing", "progress": 10.0})
        self.env.cr.commit()

        try:
            service = AzureInvoiceService(endpoint, key)
            data = service.analyze(base64.b64decode(self.file))
            if not data:
                raise UserError(_("No data returned from Azure."))

            currency_id = self._detect_currency(data.get("currency_code"))

            final_subtotal = data.get("vat_base_amount") or data.get("subtotal_amount")
            subtotal_f = self._safe_float(final_subtotal) or 0.0
            vat_f = self._safe_float(data.get("vat_amount")) or 0.0

            # VAT rate (%)
            vat_rate = 0.0
            if subtotal_f > 0 and vat_f > 0:
                vat_rate = round((vat_f / subtotal_f) * 100.0, 2)

            seller_phone = self._normalize_phone(data.get("vendor_phone"))
            customer_phone = self._normalize_phone(data.get("customer_phone"))

            self.write(
                {
                    "state": "done",
                    "progress": 100.0,
                    "ocr_run_at": fields.Datetime.now(),
                    "extracted_text": json.dumps(
                        data, indent=4, ensure_ascii=False, default=str
                    ),
                    "seller_name": data.get("vendor_name"),
                    "seller_address": data.get("vendor_address"),
                    "seller_tax_id": data.get("vendor_tax_id"),
                    "seller_phone": seller_phone,
                    "seller_website": data.get("vendor_website"),
                    "customer_name": data.get("customer_name"),
                    "customer_address": data.get("customer_address"),
                    "customer_tax_id": data.get("customer_tax_id"),
                    "customer_phone": customer_phone,
                    "document_number": data.get("invoice_id"),
                    "document_date": data.get("invoice_date"),
                    "due_date": data.get("due_date"),
                    "payment_terms": data.get("payment_terms"),
                    "reference_number": data.get("reference_number"),

                    # IMPORTANT: Many2one should use currency_id in write
                    "currency": currency_id,

                    "subtotal_excl_tax": subtotal_f,
                    "total_discount": self._safe_float(data.get("discount_amount")) or 0.0,
                    "vat_amount": vat_f,
                    "vat_rate": vat_rate,
                    "total_incl_tax": self._safe_float(data.get("total_amount")) or 0.0,
                    "confidence_score": data.get("confidence_score", 0.99),
                }
            )

            # Clear + re-add lines (enterprise-safe)
            lines_cmds = [(5, 0, 0)]
            for item in data.get("items", []):
                lines_cmds.append(
                    (
                        0,
                        0,
                        {
                            "description": item.get("description"),
                            "quantity": item.get("quantity", 1.0),
                            "unit_price": item.get("unit_price", 0.0),
                        },
                    )
                )

            self.write({"line_ids": lines_cmds})

        except Exception as e:
            _logger.exception("OCR Error")
            self.write(
                {
                    "state": "failed",
                    "progress": 0.0,
                    "ocr_error_message": str(e),
                }
            )
