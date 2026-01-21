# -*- coding: utf-8 -*-
import base64
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

        if not result.documents:
            return {}

        invoice = result.documents[0]
        fields = invoice.fields
        log = []

        def get_str(name):
            f = fields.get(name)
            return f.value_string if f else None

        def get_date(name):
            f = fields.get(name)
            return f.value_date if f else None

        def get_money(name):
            f = fields.get(name)
            return f.value_currency.amount if f else None

        # ---------------- HEADER ----------------
        vendor_name = get_str("VendorName")
        customer_name = get_str("CustomerName")
        tax_id = get_str("VendorTaxId")
        invoice_date = get_date("InvoiceDate")

        if vendor_name:
            log.append(f"[HEADER] Vendor: {vendor_name}")
        if customer_name:
            log.append(f"[HEADER] Customer: {customer_name}")
        if tax_id:
            log.append(f"[HEADER] Tax ID: {tax_id}")
        if invoice_date:
            log.append(f"[HEADER] Date: {invoice_date}")

        # ---------------- ADDRESS ----------------
        vendor_address = None
        if fields.get("VendorAddress"):
            vendor_address = str(fields["VendorAddress"].value_address)
            log.append("[HEADER] Vendor address extracted")

        # ---------------- TOTALS ----------------
        subtotal = get_money("SubTotal")
        discount = get_money("TotalDiscount")
        vat = get_money("TotalTax")
        total = get_money("InvoiceTotal")

        if subtotal is not None:
            log.append(f"[TOTALS] Subtotal: {subtotal}")
        if discount is not None:
            log.append(f"[TOTALS] Discount: {discount}")
        if vat is not None:
            log.append(f"[TOTALS] VAT: {vat}")
        if total is not None:
            log.append(f"[TOTALS] Total: {total}")

        # ---------------- ITEMS ----------------
        items = []
        if fields.get("Items"):
            for idx, item in enumerate(fields["Items"].value_array):
                obj = item.value_object

                item_data = {
                    "item_number": obj.get("ProductCode").value_string if obj.get("ProductCode") else "",
                    "description": obj.get("Description").value_string if obj.get("Description") else "",
                    "quantity": obj.get("Quantity").value_number if obj.get("Quantity") else 1.0,
                    "unit_price": obj.get("UnitPrice").value_currency.amount if obj.get("UnitPrice") else 0.0,
                }
                items.append(item_data)

                log.append(
                    f"[ITEM {idx+1}] {item_data['description']} | "
                    f"Qty={item_data['quantity']} | "
                    f"Unit={item_data['unit_price']}"
                )

        confidence = invoice.confidence if hasattr(invoice, "confidence") else 0.9
        log.append(f"[FINAL] Confidence Score = {round(confidence, 2)}")

        return {
            "vendor_name": vendor_name,
            "customer_name": customer_name,
            "tax_id": tax_id,
            "invoice_date": invoice_date,
            "vendor_address": vendor_address,
            "subtotal_amount": subtotal,
            "discount_amount": discount,
            "vat_amount": vat,
            "total_amount": total,
            "items": items,
            "confidence_score": round(confidence, 2),
            "extraction_log": "\n".join(log),
        }
