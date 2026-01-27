# -*- coding: utf-8 -*-
import base64
import os

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .azure_invoice import AzureInvoiceService


class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document"
    _order = "create_date desc"

    # ------------------------
    # BASIC
    # ------------------------
    name = fields.Char(required=True)
    file = fields.Binary(required=True, attachment=True)

    doc_type = fields.Selection(
        [("invoice", "Invoice"), ("receipt", "Receipt")],
        default="invoice",
        required=True,
        string="Doc Type",
    )

    upload_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)

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

    # ------------------------
    # ENTERPRISE: Document Identity
    # ------------------------
    document_number = fields.Char(string="Document No.")
    reference_number = fields.Char(string="Reference No.")
    document_date = fields.Date(string="Document Date", compute="_compute_document_date", store=True)

    is_tax_invoice = fields.Boolean(string="Tax Invoice", default=False)

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )

    invoice_date = fields.Date(string="Invoice Date")
    receipt_date = fields.Date(string="Receipt Date")
    receipt_number = fields.Char(string="Receipt No.")

    # ------------------------
    # PARTIES (Vendor & Customer)
    # ------------------------
    vendor_name = fields.Char(string="Vendor Name")
    vendor_branch_code = fields.Char(string="Vendor Branch Code")
    vendor_tax_id = fields.Char(string="Vendor Tax ID")
    vendor_address = fields.Text(string="Vendor Address")
    vendor_phone = fields.Char(string="Vendor Phone")
    vendor_website = fields.Char(string="Vendor Website")

    customer_name = fields.Char(string="Customer Name")
    customer_tax_id = fields.Char(string="Customer Tax ID")
    customer_address = fields.Text(string="Customer Address")
    customer_phone = fields.Char(string="Customer Phone")

    # ------------------------
    # AMOUNTS (Header-level)
    # ------------------------
    subtotal_amount = fields.Float(string="Subtotal")
    discount_total = fields.Float(string="Total Discount")
    vat_rate = fields.Float(string="VAT Rate (%)")
    vat_base_amount = fields.Float(string="VAT Base Amount")
    vat_amount = fields.Float(string="VAT Amount")
    net_amount = fields.Float(string="Net Amount (Before VAT)")
    grand_total = fields.Float(string="Grand Total")

    discount_amount = fields.Float(string="(Old) Discount", compute="_compute_compat_amounts", store=False)
    vat_percent = fields.Float(string="(Old) VAT %", compute="_compute_compat_amounts", store=False)
    total_amount = fields.Float(string="(Old) Total", compute="_compute_compat_amounts", store=False)

    # ------------------------
    # OCR META
    # ------------------------
    extracted_text = fields.Text(string="Raw OCR Text", readonly=True)
    confidence_score = fields.Float(string="Confidence Score", readonly=True)
    extraction_log = fields.Text(string="Extraction Log", readonly=True)

    ocr_engine = fields.Char(string="OCR Engine", default="azure.prebuilt-invoice", readonly=True)

    # ------------------------
    # ITEMS
    # ------------------------
    line_ids = fields.One2many("ocr.document.line", "document_id", string="Items")

    # ------------------------
    # COMPUTES
    # ------------------------
    @api.depends("doc_type", "invoice_date", "receipt_date")
    def _compute_document_date(self):
        for rec in self:
            if rec.doc_type == "receipt":
                rec.document_date = rec.receipt_date or rec.invoice_date
            else:
                rec.document_date = rec.invoice_date or rec.receipt_date

    def _compute_compat_amounts(self):
        for rec in self:
            rec.discount_amount = rec.discount_total or 0.0
            rec.vat_percent = rec.vat_rate or 0.0
            rec.total_amount = rec.grand_total or 0.0

    # ------------------------
    # HELPERS
    # ------------------------
    @staticmethod
    def _format_address(addr):
        if not addr:
            return None

        if isinstance(addr, str):
            return addr.strip() if addr.strip() else None

        if isinstance(addr, dict):
            preferred_keys = [
                "streetAddress",
                "houseNumber",
                "house",
                "road",
                "cityDistrict",
                "city",
                "state",
                "postalCode",
                "countryRegion",
            ]
            parts = []
            for k in preferred_keys:
                v = addr.get(k)
                if v and str(v).strip():
                    parts.append(str(v).strip())
            if not parts:
                for v in addr.values():
                    if v and str(v).strip():
                        parts.append(str(v).strip())
            joined = ", ".join(parts)
            return joined if joined else None

        return str(addr)

    def _smart_totals(self, parsed):
        """
        FIX: Avoid computing VAT base from SubTotal (often VAT-included in Thai receipts).
        Priority:
          1) Use vat_base_amount (TotalNet) from Azure if present
          2) Else base = grand_total - vat_amount (if both exist)
          3) Else base unknown (leave as None)
        Payable Grand Total:
          - If Azure grand_total equals base (excl VAT), fix to base + vat
        """

        subtotal_raw = parsed.get("subtotal_amount")
        discount_total = parsed.get("discount_total") or 0.0
        vat_amount = parsed.get("vat_amount")
        grand_total = parsed.get("grand_total")
        vat_base = parsed.get("vat_base_amount")

        # Ensure numeric
        def _to_float(x):
            try:
                return float(x)
            except Exception:
                return None

        subtotal_raw = _to_float(subtotal_raw)
        discount_total = _to_float(discount_total) or 0.0
        vat_amount = _to_float(vat_amount)
        grand_total = _to_float(grand_total)
        vat_base = _to_float(vat_base)

        # Compute base if missing
        if vat_base is None and grand_total is not None and vat_amount is not None:
            vat_base = round(grand_total - vat_amount, 2)

        # Fix payable total if Azure returned EXCL VAT as InvoiceTotal
        if grand_total is not None and vat_base is not None and vat_amount is not None:
            if abs(grand_total - vat_base) < 0.02:
                grand_total = round(vat_base + vat_amount, 2)

        # VAT rate from base excl VAT only
        vat_rate = 0.0
        if vat_base not in (None, 0.0) and vat_amount is not None:
            vat_rate = round((vat_amount / vat_base) * 100.0, 2)

        # Net before VAT
        net_amount = vat_base

        # Subtotal (before discount) best represented as net + discount
        # If we don't know net, keep Azure subtotal_raw
        subtotal_amount = None
        if net_amount is not None:
            subtotal_amount = round(net_amount + discount_total, 2)
        else:
            subtotal_amount = subtotal_raw

        return {
            "subtotal_amount": subtotal_amount,
            "discount_total": discount_total,
            "net_amount": net_amount,
            "vat_base_amount": vat_base,
            "vat_amount": vat_amount,
            "vat_rate": vat_rate,
            "grand_total": grand_total,
        }

    # ------------------------
    # ACTIONS
    # ------------------------
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
                        "item_no": item.get("item_no") or item.get("item_number") or "",
                        "description": item.get("description") or "",
                        "quantity": item.get("quantity", 1.0) or 1.0,
                        "unit_price": item.get("unit_price", 0.0) or 0.0,
                        "discount": item.get("discount", 0.0) or 0.0,
                        "vat_rate": item.get("vat_rate", 0.0) or 0.0,
                    })

                # Address formatting
                vendor_addr = self._format_address(parsed.get("vendor_address"))
                customer_addr = self._format_address(parsed.get("customer_address"))

                # Currency
                currency_code = parsed.get("currency_code")
                currency_id = doc.currency_id.id
                if currency_code:
                    cur = self.env["res.currency"].search([("name", "=", currency_code)], limit=1)
                    if cur:
                        currency_id = cur.id

                # Doc number
                doc_no = parsed.get("document_number") or parsed.get("invoice_number") or parsed.get("receipt_number")

                # FIXED TOTALS
                totals = self._smart_totals(parsed)

                write_vals = {
                    "status": "completed",
                    "progress": 100,

                    # document identity
                    "document_number": doc_no,
                    "reference_number": parsed.get("reference_number"),
                    "invoice_date": parsed.get("invoice_date"),
                    "receipt_date": parsed.get("receipt_date"),
                    "receipt_number": parsed.get("receipt_number"),
                    "is_tax_invoice": bool(parsed.get("is_tax_invoice")),
                    "currency_id": currency_id,

                    # vendor
                    "vendor_name": parsed.get("vendor_name"),
                    "vendor_branch_code": parsed.get("vendor_branch_code"),
                    "vendor_tax_id": parsed.get("vendor_tax_id"),
                    "vendor_address": vendor_addr,
                    "vendor_phone": parsed.get("vendor_phone"),
                    "vendor_website": parsed.get("vendor_website"),

                    # customer
                    "customer_name": parsed.get("customer_name"),
                    "customer_tax_id": parsed.get("customer_tax_id"),
                    "customer_address": customer_addr,
                    "customer_phone": parsed.get("customer_phone"),

                    # amounts (fixed)
                    "subtotal_amount": totals["subtotal_amount"],
                    "discount_total": totals["discount_total"],
                    "vat_rate": totals["vat_rate"],
                    "vat_base_amount": totals["vat_base_amount"],
                    "vat_amount": totals["vat_amount"],
                    "net_amount": totals["net_amount"],
                    "grand_total": totals["grand_total"],

                    # meta
                    "confidence_score": parsed.get("confidence_score"),
                    "extraction_log": parsed.get("extraction_log"),
                    "extracted_text": parsed.get("raw_text"),
                }

                doc.write(write_vals)

            except Exception as e:
                doc.write({
                    "status": "error",
                    "progress": 100,
                    "confidence_score": 0.0,
                    "extraction_log": str(e),
                })

        return True
