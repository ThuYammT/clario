# -*- coding: utf-8 -*-
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest


class AzureInvoiceService:
    """
    Wrapper around Azure Document Intelligence - Prebuilt Invoice
    """

    def __init__(self, endpoint: str, key: str):
        self.client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )

    def analyze(self, file_bytes: bytes) -> dict:
        poller = self.client.begin_analyze_document(
            "prebuilt-invoice",
            AnalyzeDocumentRequest(bytes_source=file_bytes),
        )
        result = poller.result()

        raw_text = None
        try:
            if hasattr(result, "content"):
                raw_text = result.content
        except Exception:
            raw_text = None

        if not result.documents:
            return {"raw_text": raw_text or ""}

        invoice = result.documents[0]
        fields = invoice.fields or {}
        log = []

        def fget(name):
            return fields.get(name)

        def get_str(name):
            f = fget(name)
            return f.value_string if f else None

        def get_date(name):
            f = fget(name)
            return f.value_date if f else None

        def get_currency(name):
            """
            Returns (amount, currency_code) if currency is present.
            """
            f = fget(name)
            if not f or not f.value_currency:
                return (None, None)
            cur = f.value_currency
            return (cur.amount, getattr(cur, "currency_code", None))

        def get_money_amount(name):
            amt, _code = get_currency(name)
            return amt

        def get_first_str(candidates):
            for key in candidates:
                v = get_str(key)
                if v:
                    return v
            return None

        def get_first_date(candidates):
            for key in candidates:
                v = get_date(key)
                if v:
                    return v
            return None

        # ---------------- HEADER / IDs ----------------
        vendor_name = get_str("VendorName")
        customer_name = get_str("CustomerName")

        document_number = get_first_str(["InvoiceId", "InvoiceNumber", "ReceiptNumber", "ReferenceNumber"])
        reference_number = get_first_str(["PurchaseOrder", "Reference", "ReferenceNumber", "OrderNumber"])

        invoice_date = get_first_date(["InvoiceDate", "Date"])
        receipt_date = get_first_date(["ReceiptDate"])
        receipt_number = get_str("ReceiptNumber") or (document_number if document_number else None)

        vendor_tax_id = get_first_str(["VendorTaxId", "TaxId", "VendorVATNumber"])
        customer_tax_id = get_first_str(["CustomerTaxId", "CustomerVATNumber"])

        vendor_branch_code = get_first_str(["VendorAddressRecipient", "VendorBranch", "VendorBranchCode"])
        is_tax_invoice = True if vendor_tax_id else False

        if vendor_name:
            log.append(f"[HEADER] Vendor: {vendor_name}")
        if customer_name:
            log.append(f"[HEADER] Customer: {customer_name}")
        if document_number:
            log.append(f"[HEADER] Document No: {document_number}")
        if reference_number:
            log.append(f"[HEADER] Ref No: {reference_number}")
        if vendor_tax_id:
            log.append(f"[HEADER] Vendor Tax ID: {vendor_tax_id}")
        if invoice_date:
            log.append(f"[HEADER] Invoice Date: {invoice_date}")

        # ---------------- CONTACT ----------------
        vendor_phone = get_first_str(["VendorPhoneNumber", "VendorPhone", "PhoneNumber"])
        customer_phone = get_first_str(["CustomerPhoneNumber", "CustomerPhone"])
        vendor_website = get_first_str(["VendorWebsite", "Website"])

        # ---------------- ADDRESS ----------------
        vendor_address = None
        if fget("VendorAddress") and fget("VendorAddress").value_address:
            addr_obj = fget("VendorAddress").value_address
            vendor_address = {
                "streetAddress": getattr(addr_obj, "street_address", None),
                "houseNumber": getattr(addr_obj, "house_number", None),
                "road": getattr(addr_obj, "road", None),
                "cityDistrict": getattr(addr_obj, "district", None),
                "city": getattr(addr_obj, "city", None),
                "state": getattr(addr_obj, "state", None),
                "postalCode": getattr(addr_obj, "postal_code", None),
                "countryRegion": getattr(addr_obj, "country_region", None),
            }
            log.append("[HEADER] Vendor address extracted")

        customer_address = None
        if fget("CustomerAddress") and fget("CustomerAddress").value_address:
            addr_obj = fget("CustomerAddress").value_address
            customer_address = {
                "streetAddress": getattr(addr_obj, "street_address", None),
                "houseNumber": getattr(addr_obj, "house_number", None),
                "road": getattr(addr_obj, "road", None),
                "cityDistrict": getattr(addr_obj, "district", None),
                "city": getattr(addr_obj, "city", None),
                "state": getattr(addr_obj, "state", None),
                "postalCode": getattr(addr_obj, "postal_code", None),
                "countryRegion": getattr(addr_obj, "country_region", None),
            }
            log.append("[HEADER] Customer address extracted")

        # ---------------- TOTALS ----------------
        subtotal, cur1 = get_currency("SubTotal")
        discount_total, cur2 = get_currency("TotalDiscount")
        vat_amount, cur3 = get_currency("TotalTax")
        grand_total, cur4 = get_currency("InvoiceTotal")

        currency_code = cur4 or cur3 or cur2 or cur1

        # FIX: VAT base should NOT fall back to SubTotal (often VAT-included on receipts)
        # Prefer TotalNet; otherwise compute as GrandTotal - VAT
        vat_base_amount = get_money_amount("TotalNet")
        if vat_base_amount is not None:
            log.append("[VAT] Base from TotalNet")
        elif grand_total is not None and vat_amount is not None:
            vat_base_amount = round(float(grand_total) - float(vat_amount), 2)
            log.append("[VAT] Base from InvoiceTotal - VAT")
        else:
            vat_base_amount = None
            log.append("[VAT] Base unavailable (missing TotalNet and/or InvoiceTotal/TotalTax)")

        # VAT rate only from base excl VAT
        vat_rate = None
        if vat_amount is not None and vat_base_amount not in (None, 0):
            try:
                vat_rate = round((float(vat_amount) / float(vat_base_amount)) * 100.0, 2)
            except Exception:
                vat_rate = None

        if subtotal is not None:
            log.append(f"[TOTALS] Subtotal(raw): {subtotal}")
        if discount_total is not None:
            log.append(f"[TOTALS] Discount: {discount_total}")
        if vat_amount is not None:
            log.append(f"[TOTALS] VAT: {vat_amount}")
        if grand_total is not None:
            log.append(f"[TOTALS] InvoiceTotal: {grand_total}")
        if vat_base_amount is not None:
            log.append(f"[TOTALS] VAT Base (excl): {vat_base_amount}")
        if vat_rate is not None:
            log.append(f"[TOTALS] VAT Rate: {vat_rate}")
        if currency_code:
            log.append(f"[TOTALS] Currency: {currency_code}")

        # ---------------- ITEMS ----------------
        items = []
        if fget("Items"):
            try:
                for idx, item in enumerate(fget("Items").value_array):
                    obj = item.value_object or {}

                    product_code = obj.get("ProductCode").value_string if obj.get("ProductCode") else ""
                    desc = obj.get("Description").value_string if obj.get("Description") else ""

                    qty = obj.get("Quantity").value_number if obj.get("Quantity") else 1.0
                    unit_price = (
                        obj.get("UnitPrice").value_currency.amount
                        if obj.get("UnitPrice") and obj.get("UnitPrice").value_currency
                        else 0.0
                    )

                    line_discount = 0.0
                    if obj.get("Discount") and obj.get("Discount").value_currency:
                        line_discount = obj.get("Discount").value_currency.amount or 0.0

                    # Many invoices won't have per-line tax rate; default to header vat_rate if available.
                    line_tax_rate = 0.0
                    if obj.get("TaxRate") and obj.get("TaxRate").value_number is not None:
                        line_tax_rate = float(obj.get("TaxRate").value_number)
                    elif vat_rate is not None:
                        line_tax_rate = float(vat_rate)

                    item_data = {
                        "item_no": product_code,
                        "description": desc,
                        "quantity": qty if qty is not None else 1.0,
                        "unit_price": unit_price if unit_price is not None else 0.0,
                        "discount": line_discount,
                        "vat_rate": line_tax_rate,
                    }
                    items.append(item_data)

                    log.append(
                        f"[ITEM {idx+1}] {desc} | Qty={item_data['quantity']} | Unit={item_data['unit_price']}"
                    )
            except Exception as e:
                log.append(f"[ITEMS] Failed parsing items: {e}")

        confidence = getattr(invoice, "confidence", 0.9)
        log.append(f"[FINAL] Confidence Score = {round(confidence, 2)}")

        return {
            # identity
            "document_number": document_number,
            "reference_number": reference_number,
            "invoice_date": invoice_date,
            "receipt_date": receipt_date,
            "receipt_number": receipt_number,
            "is_tax_invoice": is_tax_invoice,
            "currency_code": currency_code,

            # vendor
            "vendor_name": vendor_name,
            "vendor_branch_code": vendor_branch_code,
            "vendor_tax_id": vendor_tax_id,
            "vendor_address": vendor_address,
            "vendor_phone": vendor_phone,
            "vendor_website": vendor_website,

            # customer
            "customer_name": customer_name,
            "customer_tax_id": customer_tax_id,
            "customer_address": customer_address,
            "customer_phone": customer_phone,

            # amounts (raw Azure + computed)
            "subtotal_amount": subtotal,
            "discount_total": discount_total,
            "vat_rate": vat_rate,
            "vat_base_amount": vat_base_amount,
            "vat_amount": vat_amount,
            "grand_total": grand_total,

            # items/meta
            "items": items,
            "confidence_score": round(confidence, 2),
            "extraction_log": "\n".join(log),
            "raw_text": raw_text or "",
        }
