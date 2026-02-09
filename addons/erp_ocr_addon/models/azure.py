# -*- coding: utf-8 -*-
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import logging
import re

_logger = logging.getLogger(__name__)


class AzureInvoiceService:
    """
    Advanced Wrapper for Azure Document Intelligence

    Features:
    - Smart Address Formatting (Thai-friendly)
    - Multi-key field search (Tax IDs / Phones)
    - Currency Extraction
    - SAFE OCR fallback for phone numbers (label-based, Thai rules)
    """

    def __init__(self, endpoint: str, key: str):
        self.client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )

    # ======================================================
    # PHONE EXTRACTION (SAFE OCR FALLBACK)
    # ======================================================
    def _normalize_phone(self, s: str) -> str:
        if not s:
            return ""
        s = s.strip()
        s = re.sub(r"[ \t\r\n\-\(\)\.]", "", s)
        return s

    def _extract_phone_from_text(self, text: str) -> str | None:
        """
        Extract phone numbers ONLY near phone labels.
        Prevents invoice numbers / dates from being mistaken as phones.
        """
        if not text:
            return None

        # Label-based extraction (BEST & SAFEST)
        label_patterns = [
            r"(?:เบอร์โทร|เบอรโทร|โทรศัพท์|โทร|Tel\.?|Telephone|Phone)"
            r"\s*[:\|]?\s*([+0-9][0-9 \-\(\)\.]{7,})"
        ]

        for pat in label_patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                cand = self._normalize_phone(m.group(1))

                # Thai phone rules
                if cand.startswith("+66") and 9 <= len(cand) <= 11:
                    return cand
                if cand.startswith("0") and 9 <= len(cand) <= 10:
                    return cand

        # Secondary scan (still strict)
        # Accept ONLY Thai-looking numbers, not generic digits
        loose = re.findall(r"(\+66[0-9]{8,9}|0[0-9]{8,9})", text)
        for cand in loose:
            cand = self._normalize_phone(cand)
            if cand.startswith("+66") or cand.startswith("0"):
                return cand

        return None

    # ======================================================
    # MAIN ANALYSIS
    # ======================================================
    def analyze(self, file_bytes: bytes) -> dict:
        poller = self.client.begin_analyze_document(
            "prebuilt-invoice",
            AnalyzeDocumentRequest(bytes_source=file_bytes),
        )
        result = poller.result()

        raw_text = getattr(result, "content", None)

        if not result.documents:
            return {"raw_text": raw_text or ""}

        invoice = result.documents[0]
        fields = invoice.fields or {}

        # ==================================================
        # HELPER FUNCTIONS
        # ==================================================
        def fget(name):
            return fields.get(name)

        def get_str(name):
            f = fget(name)
            return f.value_string if f else None

        def get_date(name):
            f = fget(name)
            return f.value_date if f else None

        def get_currency(name):
            f = fget(name)
            if not f or not f.value_currency:
                return (None, None)
            cur = f.value_currency
            return (cur.amount, getattr(cur, "currency_code", None))

        def get_first_str(candidates):
            for key in candidates:
                v = get_str(key)
                if v:
                    return v
            return None

        def format_address(field_name):
            f = fget(field_name)
            if not f:
                return None

            if f.value_address:
                addr = f.value_address
                parts = []
                if getattr(addr, "house_number", None):
                    parts.append(f"เลขที่ {addr.house_number}")
                if getattr(addr, "road", None):
                    parts.append(addr.road)
                if getattr(addr, "city_district", None):
                    parts.append(f"เขต{addr.city_district}")
                if getattr(addr, "city", None):
                    parts.append(addr.city)
                if getattr(addr, "postal_code", None):
                    parts.append(addr.postal_code)
                if getattr(addr, "country_region", None):
                    parts.append(addr.country_region)

                joined = " ".join(p for p in parts if p).strip()
                if joined:
                    return joined

            return f.content if f.content else None

        # ==================================================
        # EXTRACTION START
        # ==================================================

        # --- Parties ---
        vendor_name = get_str("VendorName")
        customer_name = get_str("CustomerName")

        vendor_tax_id = get_first_str(
            ["VendorTaxId", "TaxId", "VendorVATNumber"]
        )
        customer_tax_id = get_first_str(
            ["CustomerTaxId", "CustomerVATNumber"]
        )

        # --- Phones ---
        vendor_phone = (
            get_first_str(["VendorPhoneNumber", "VendorPhone"])
            or self._extract_phone_from_text(raw_text)
        )

        # IMPORTANT:
        # Do NOT fallback customer phone from raw OCR
        # (Most receipts only show vendor phone)
        customer_phone = get_first_str(
            ["CustomerPhoneNumber", "CustomerPhone"]
        )

        vendor_website = get_first_str(["VendorWebsite", "Website"])

        # --- Addresses ---
        vendor_address = format_address("VendorAddress")
        customer_address = format_address("CustomerAddress")

        # --- Document Info ---
        document_number = get_first_str(
            ["InvoiceId", "InvoiceNumber", "ReceiptNumber", "ReferenceNumber"]
        )
        reference_number = get_first_str(
            ["PurchaseOrder", "Reference", "ReferenceNumber"]
        )

        invoice_date = get_date("InvoiceDate") or get_date("Date")
        due_date = get_date("DueDate")
        payment_terms = get_str("PaymentTerm") or get_str("PaymentTerms")

        # --- Financials & Currency ---
        subtotal, c1 = get_currency("SubTotal")
        discount, c2 = get_currency("TotalDiscount")
        vat, c3 = get_currency("TotalTax")
        total, c4 = get_currency("InvoiceTotal")

        currency_code = c4 or c3 or c2 or c1

        # --- VAT Base Calculation ---
        vat_base_amount = None
        net_field = get_currency("TotalNet")

        if net_field[0] is not None:
            vat_base_amount = net_field[0]
        elif total is not None and vat is not None:
            vat_base_amount = round(float(total) - float(vat), 2)

        # --- Line Items ---
        items = []
        if fget("Items") and fget("Items").value_array:
            for item in fget("Items").value_array:
                obj = item.value_object
                if not obj:
                    continue

                def l_str(k):
                    return obj.get(k).value_string if obj.get(k) else ""

                def l_num(k):
                    return obj.get(k).value_number if obj.get(k) else 1.0

                def l_money(k):
                    return (
                        obj.get(k).value_currency.amount
                        if obj.get(k) and obj.get(k).value_currency
                        else 0.0
                    )

                items.append({
                    "description": l_str("Description"),
                    "product_code": l_str("ProductCode"),
                    "quantity": l_num("Quantity"),
                    "unit_price": l_money("UnitPrice"),
                    "amount": l_money("Amount") or l_money("Tax"),
                })

        confidence = invoice.confidence if hasattr(invoice, "confidence") else 0.9

        # ==================================================
        # RETURN
        # ==================================================
        return {
            "raw_text": raw_text,
            "confidence_score": confidence,
            "currency_code": currency_code,

            "invoice_id": document_number,
            "reference_number": reference_number,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "payment_terms": payment_terms,

            "vendor_name": vendor_name,
            "vendor_tax_id": vendor_tax_id,
            "vendor_address": vendor_address,
            "vendor_phone": vendor_phone,
            "vendor_website": vendor_website,

            "customer_name": customer_name,
            "customer_tax_id": customer_tax_id,
            "customer_address": customer_address,
            "customer_phone": customer_phone,

            "subtotal_amount": subtotal,
            "discount_amount": discount,
            "vat_amount": vat,
            "total_amount": total,
            "vat_base_amount": vat_base_amount,

            "items": items,
        }
