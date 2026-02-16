# -*- coding: utf-8 -*-
import os
import base64
import json
import logging
import hashlib
import re

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
        if not addr_struct or not isinstance(addr_struct, dict):
            return None

        # Prefer RAW if exists (cleanest full address)
        raw = addr_struct.get("raw")
        if raw:
            raw = raw.replace("\n", " ")
            raw = re.sub(r"\s+", " ", raw).strip()
            return raw

        parts = []
        seen = set()

        for key in [
            "house",
            "unit",
            "street_address",
            "house_number",
            "road",
            "city_district",
            "city",
            "postal_code",
            "country_region",
        ]:
            val = addr_struct.get(key)
            if val:
                clean_val = val.replace("\n", " ")
                clean_val = re.sub(r"\s+", " ", clean_val).strip()

                # prevent duplication
                if clean_val not in seen:
                    seen.add(clean_val)
                    parts.append(clean_val)

        return ", ".join(parts) if parts else None

    # ======================================================
    # STRUCTURAL CLEANING (Non-Financial Deterministic Fixes)
    # ======================================================

    def _clean_vendor_name(self, name):
        if not name:
            return name

        name = name.replace("\n", " ").strip()

        # Remove anything after pipe containing branch info
        name = re.sub(r"\|\s*.*?(รหัสสาขา|Branch).*?$", "", name, flags=re.IGNORECASE)

        # Remove duplicate spaces
        name = re.sub(r"\s+", " ", name).strip()

        return name



    def _clean_text_field(self, value):
        if not value:
            return value
        value = value.replace("\n", " ")
        value = re.sub(r"\s+", " ", value).strip()
        return value
    
    def _fallback_extract_customer_tax_id(self, data):
        """
        Deterministic fallback for Thai receipts.
        Rules:
        1. Prefer explicit Customer ID label
        2. Avoid picking vendor tax ID
        3. Only fallback to generic 13-digit if safe
        """

        if data.get("customer_tax_id"):
            return data.get("customer_tax_id")

        raw_text = data.get("raw_text") or ""
        vendor_tax = data.get("vendor_tax_id")

        # 1️⃣ STRICT match: Customer ID label only
        match = re.search(
            r"Customer\s*ID\s*[:\-]?\s*\n?\s*(\d{13})",
            raw_text,
            re.IGNORECASE
        )
        if match:
            return match.group(1)

        # 2️⃣ Thai label for customer tax
        match = re.search(
            r"ลูกค้า.*?(?:Tax\s*ID|เลขประจำตัวผู้เสียภาษี).*?(\d{13})",
            raw_text,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            val = match.group(1)
            if val != vendor_tax:
                return val

        # 3️⃣ SAFE fallback: find all 13-digit numbers except vendor tax
        candidates = re.findall(r"\b\d{13}\b", raw_text)
        for num in candidates:
            if num != vendor_tax:
                return num

        return None




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
            # ==========================================
            # APPLY STRUCTURAL CLEANING
            # ==========================================
            data = dict(raw_data)  # later: apply corrections here
            # Clean vendor name
            data["vendor_name"] = self._clean_vendor_name(data.get("vendor_name"))

            # Clean customer name
            data["customer_name"] = self._clean_text_field(data.get("customer_name"))

            # Clean website
            data["vendor_website"] = self._clean_text_field(data.get("vendor_website"))

            # Clean tax ids
            data["vendor_tax_id"] = self._clean_text_field(data.get("vendor_tax_id"))
            data["customer_tax_id"] = self._clean_text_field(data.get("customer_tax_id"))
            # ==========================================
            # DISCOUNT FALLBACK (Flexible Thai Pattern)
            # ==========================================
            if not data.get("discount_amount"):
                raw_text = data.get("raw_text") or ""

                discount_keywords = [
                    "ส่วนลด",
                    "ลดราคา",
                    "หักส่วนลด",
                    "โปรโมชั่น",
                    "โปรโมชัน",
                    "Discount",
                    "Promo"
                ]

                pattern = r"(?:%s)[^\n]*\n?\s*[-]?\s*([0-9]+\.[0-9]{2})" % "|".join(discount_keywords)

                m = re.search(pattern, raw_text, re.IGNORECASE)

                if m:
                    try:
                        data["discount_amount"] = float(m.group(1))
                    except Exception:
                        pass

            # Deterministic fallback for Thai receipts
            if not data.get("customer_tax_id"):
                fallback_tax = self._fallback_extract_customer_tax_id(data)
                if fallback_tax:
                    data["customer_tax_id"] = fallback_tax


            self.post_processed_response = json.dumps(
            data, indent=4, ensure_ascii=False, default=str)


            if not data:
                raise UserError(_("No data returned from Azure."))

            currency = self._detect_currency(data.get("currency_code"))

            # Totals (keep your current logic)
            # ======================================================
            # ======================================================
            # FINANCIALS (stable deterministic logic)
            # ======================================================
            # ======================================================
            # FINANCIALS — DETERMINISTIC (LINE FIRST + VAT-AWARE)
            # ======================================================

            discount_val = self._safe_float(data.get("discount_amount")) or 0.0
            vat_val = self._safe_float(data.get("vat_amount")) or 0.0

            azure_subtotal = self._safe_float(data.get("subtotal_amount"))
            azure_total = self._safe_float(data.get("total_amount"))

            # 1) Sum items
            items_sum = 0.0
            items_list = data.get("items") or []
            found_any = False

            for item in items_list:
                amt = self._safe_float(item.get("amount"))
                qty = self._safe_float(item.get("quantity"))
                unit = self._safe_float(item.get("unit_price"))

                if amt is not None:
                    items_sum += amt
                    found_any = True
                elif qty is not None and unit is not None:
                    items_sum += qty * unit
                    found_any = True

            items_sum = round(items_sum, 2) if found_any else None

            # 2) Detect if items_sum is "incl VAT" or "excl VAT"
            # Heuristic: if (items_sum - discount) ~= net paid (often Azure subtotal is net paid for Thai ABB),
            # then items_sum is likely INCL VAT (like Lotus receipt).
            items_sum_includes_vat = False
            if items_sum is not None and azure_subtotal is not None and abs((items_sum - discount_val) - azure_subtotal) < 0.02:
                items_sum_includes_vat = True
            elif items_sum is not None and azure_total is not None and abs((items_sum - discount_val) - azure_total) < 0.02:
                items_sum_includes_vat = True

            # 3) Compute the four fields with consistent meaning
            # We want:
            # A) subtotal_excl_vat_excl_discount
            # B) subtotal_incl_vat_excl_discount
            # C) subtotal_excl_vat_incl_discount
            # D) total_payable (incl VAT, incl discount)

            subtotal_excl_vat_excl_discount = 0.0
            subtotal_incl_vat_excl_discount = 0.0
            subtotal_excl_vat_incl_discount = 0.0
            total_payable = 0.0

            if items_sum is not None:
                if items_sum_includes_vat:
                    # items_sum = gross incl VAT (before discount)
                    gross_incl_vat = items_sum
                    net_incl_vat = round(gross_incl_vat - discount_val, 2)

                    gross_excl_vat = round(gross_incl_vat - vat_val, 2) if vat_val else gross_incl_vat
                    net_excl_vat = round(net_incl_vat - vat_val, 2) if vat_val else net_incl_vat

                    subtotal_excl_vat_excl_discount = gross_excl_vat
                    subtotal_incl_vat_excl_discount = gross_incl_vat
                    subtotal_excl_vat_incl_discount = max(net_excl_vat, 0.0)
                    total_payable = net_incl_vat
                else:
                    # items_sum = gross excl VAT (before discount)
                    gross_excl_vat = items_sum
                    gross_incl_vat = round(gross_excl_vat + vat_val, 2)

                    net_excl_vat = round(gross_excl_vat - discount_val, 2)
                    net_incl_vat = round(net_excl_vat + vat_val, 2)

                    subtotal_excl_vat_excl_discount = gross_excl_vat
                    subtotal_incl_vat_excl_discount = gross_incl_vat
                    subtotal_excl_vat_incl_discount = max(net_excl_vat, 0.0)
                    total_payable = net_incl_vat
            else:
                # fallback if no items: use Azure values carefully
                # Prefer net paid if we have it
                if azure_subtotal is not None and vat_val is not None:
                    # assume azure_subtotal might be net incl VAT (Thai ABB case)
                    net_incl_vat = azure_subtotal
                    net_excl_vat = round(net_incl_vat - vat_val, 2)

                    subtotal_excl_vat_incl_discount = max(net_excl_vat, 0.0)
                    total_payable = net_incl_vat
                    # gross unknown -> set to net
                    subtotal_excl_vat_excl_discount = subtotal_excl_vat_incl_discount
                    subtotal_incl_vat_excl_discount = total_payable
                elif azure_total is not None:
                    total_payable = azure_total
                    subtotal_incl_vat_excl_discount = azure_total
                    subtotal_excl_vat_excl_discount = round(azure_total - vat_val, 2) if vat_val else azure_total
                    subtotal_excl_vat_incl_discount = max(subtotal_excl_vat_excl_discount - discount_val, 0.0)

            # Debug log visible in UI field
            debug_text = f"""
            items_sum: {items_sum}
            items_sum_includes_vat: {items_sum_includes_vat}
            azure_subtotal: {azure_subtotal}
            azure_total: {azure_total}
            vat: {vat_val}
            discount: {discount_val}

            subtotal_excl_vat_excl_discount: {subtotal_excl_vat_excl_discount}
            subtotal_incl_vat_excl_discount: {subtotal_incl_vat_excl_discount}
            subtotal_excl_vat_incl_discount: {subtotal_excl_vat_incl_discount}
            total_payable: {total_payable}
            """
            self.extraction_log = debug_text

            _logger.info("OCR Financial Debug:\n%s", debug_text)





            # Phones
            v_phone = self._normalize_phone(data.get("vendor_phone"))
            c_phone = self._normalize_phone(data.get("customer_phone"))


            # Structured addresses -> formatted strings
            vendor_addr = self._format_structured_address(data.get("vendor_address_struct"))
            customer_addr = self._format_structured_address(data.get("customer_address_struct"))
            vendor_addr = self._clean_text_field(vendor_addr)
            customer_addr = self._clean_text_field(customer_addr)

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
                "confidence_score": (self._safe_float(data.get("confidence_score")) or 0.0),
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
