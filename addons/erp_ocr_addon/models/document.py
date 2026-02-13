# -*- coding: utf-8 -*-
import os
import base64
import json
import logging
import hashlib

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
    def _normalize_phone(self, phone):
        if not phone:
            return phone
        phone = str(phone).strip()
        for ch in [" ", "-", "(", ")", ".", "\t", "\n", "\r"]:
            phone = phone.replace(ch, "")
        return phone

    def _safe_float(self, v):
        try:
            if v is None or v == "":
                return None
            return float(v)
        except Exception:
            return None

    def _detect_currency(self, code_from_azure):
        if code_from_azure:
            cur = self.env["res.currency"].search([("name", "=", code_from_azure)], limit=1)
            if cur:
                return cur
        return self.env.company.currency_id

    def _format_structured_address(self, addr_struct):
        """
        Azure returns value_address with many components.
        We format into a clean display string for Odoo Text fields.
        """
        if not addr_struct or not isinstance(addr_struct, dict):
            return None

        parts = []

        # Nice order for Thailand docs
        # (keep it simple + non-destructive)
        for key in ["house", "unit", "street_address", "house_number", "road", "city_district", "city", "postal_code", "country_region"]:
            val = addr_struct.get(key)
            if val:
                parts.append(str(val).strip())

        # If everything empty, fallback to raw content if provided
        if not parts:
            raw = addr_struct.get("raw")
            return raw.strip() if raw else None

        # de-duplicate neighboring duplicates
        cleaned = []
        for p in parts:
            if not cleaned or cleaned[-1] != p:
                cleaned.append(p)

        return ", ".join(cleaned)

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
    def _find_or_create_vendor_partner(self):
        self.ensure_one()

        if not self.vendor_name:
            raise UserError(_("Vendor information is missing."))

        vat = (self.vendor_tax_id or "").strip() or False
        phone = self._normalize_phone(self.vendor_phone)

        domain = [("supplier_rank", ">", 0)]
        if vat:
            domain = [("vat", "=", vat)] + domain
        else:
            domain = [("name", "=", self.vendor_name)] + domain

        partner = self.env["res.partner"].search(domain, limit=1)

        if not partner:
            partner = self.env["res.partner"].create({
                "name": self.vendor_name,
                "vat": vat,
                "phone": phone,
                "website": self.vendor_website,
                "supplier_rank": 1,
            })
        else:
            upd = {}
            if vat and not partner.vat:
                upd["vat"] = vat
            if phone and not partner.phone:
                upd["phone"] = phone
            if self.vendor_website and not partner.website:
                upd["website"] = self.vendor_website
            if upd:
                partner.write(upd)

        return partner

    def action_create_vendor_bill(self):
        self.ensure_one()

        if self.vendor_bill_id:
            raise UserError(_("Vendor Bill already created."))

        partner = self._find_or_create_vendor_partner()

        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append((0, 0, {
                "name": line.description or "",
                "quantity": line.quantity or 1.0,
                "price_unit": line.unit_price or 0.0,
            }))

        if not invoice_lines:
            raise UserError(_("No line items found."))

        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": self.invoice_date,
            "invoice_origin": self.name,
            "invoice_line_ids": invoice_lines,
        })

        self.vendor_bill_id = bill.id

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
        }

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
            raw_data = service.analyze(base64.b64decode(self.file))

            # Store exact Azure output
            self.azure_raw_response = json.dumps(raw_data, indent=4, ensure_ascii=False, default=str)

            data = dict(raw_data)  # later: apply corrections here

            # Store post-processed
            self.post_processed_response = json.dumps(data, indent=4, ensure_ascii=False, default=str)

            if not data:
                raise UserError(_("No data returned from Azure."))

            currency = self._detect_currency(data.get("currency_code"))

            # Totals (keep your current logic)
            vat_base = self._safe_float(data.get("vat_base_amount"))
            subtotal = self._safe_float(data.get("subtotal_amount"))
            final_subtotal = vat_base if vat_base is not None else (subtotal if subtotal is not None else 0.0)

            vat_val = self._safe_float(data.get("vat_amount"))
            vat_val = vat_val if vat_val is not None else 0.0

            # Phones
            v_phone = self._normalize_phone(data.get("vendor_phone"))
            c_phone = self._normalize_phone(data.get("customer_phone"))

            # Structured addresses -> formatted strings
            vendor_addr = self._format_structured_address(data.get("vendor_address_struct"))
            customer_addr = self._format_structured_address(data.get("customer_address_struct"))

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
                "currency_id": currency.id,
                "currency_code": data.get("currency_code") or currency.name,
                "vat_base_amount": final_subtotal,
                "subtotal_amount": final_subtotal,
                "discount_amount": (self._safe_float(data.get("discount_amount")) or 0.0),
                "vat_amount": vat_val,
                "total_amount": (self._safe_float(data.get("total_amount")) or 0.0),

                # confidence
                "confidence_score": (self._safe_float(data.get("confidence_score")) or 0.0),
            })

            # Replace lines safely
            lines_cmds = [(5, 0, 0)]
            for item in (data.get("items") or []):
                lines_cmds.append((0, 0, {
                    "product_code": item.get("product_code"),
                    "description": item.get("description"),
                    "quantity": item.get("quantity", 1.0),
                    "unit_price": item.get("unit_price", 0.0),
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
