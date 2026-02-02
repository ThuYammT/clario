from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import logging

_logger = logging.getLogger(__name__)

class AzureInvoiceService:
    """
    Wrapper around Azure Document Intelligence - Prebuilt Invoice
    """
    def __init__(self, endpoint: str, key: str):
        self.client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )

    def _get_str(self, fields, name):
        f = fields.get(name)
        return f.value_string if f and f.value_string else None

    def _get_date(self, fields, name):
        f = fields.get(name)
        return f.value_date if f and f.value_date else None

    def _get_money(self, fields, name):
        f = fields.get(name)
        if f and f.value_currency:
            return f.value_currency.amount
        return None

    def _format_address(self, addr):
        if not addr: return None
        parts = []
        if addr.house_number: parts.append(f"เลขที่ {addr.house_number}")
        if addr.road: parts.append(addr.road)
        if addr.suburb: parts.append(addr.suburb)
        if addr.city_district: parts.append(f"เขต{addr.city_district}")
        if addr.city: parts.append(addr.city)
        if addr.postal_code: parts.append(addr.postal_code)
        return " ".join(parts).strip()

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

        # Extraction Logic
        vendor_name = self._get_str(fields, "VendorName")
        customer_name = self._get_str(fields, "CustomerName")
        tax_id = self._get_str(fields, "VendorTaxId")
        invoice_date = self._get_date(fields, "InvoiceDate")
        invoice_id = self._get_str(fields, "InvoiceId")
        due_date = self._get_date(fields, "DueDate")

        # Address
        vendor_address = None
        if fields.get("VendorAddress") and fields["VendorAddress"].value_address:
            vendor_address = self._format_address(fields["VendorAddress"].value_address)
        elif self._get_str(fields, "VendorAddress"):
            vendor_address = self._get_str(fields, "VendorAddress")

        # Totals
        subtotal = self._get_money(fields, "SubTotal")
        discount = self._get_money(fields, "TotalDiscount")
        vat = self._get_money(fields, "TotalTax")
        total = self._get_money(fields, "InvoiceTotal")

        # Items
        items = []
        if fields.get("Items") and fields["Items"].value_array:
            for item in fields["Items"].value_array:
                obj = item.value_object
                items.append({
                    "description": obj.get("Description").value_string if obj.get("Description") else "Item",
                    "quantity": obj.get("Quantity").value_number if obj.get("Quantity") else 1.0,
                    "unit_price": obj.get("UnitPrice").value_currency.amount if obj.get("UnitPrice") and obj.get("UnitPrice").value_currency else 0.0,
                    "amount": obj.get("Amount").value_currency.amount if obj.get("Amount") and obj.get("Amount").value_currency else 0.0,
                    "product_code": obj.get("ProductCode").value_string if obj.get("ProductCode") else ""
                })

        confidence = invoice.confidence if hasattr(invoice, "confidence") else 0.9

        return {
            "vendor_name": vendor_name,
            "customer_name": customer_name,
            "tax_id": tax_id,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "invoice_id": invoice_id,
            "vendor_address": vendor_address,
            "subtotal_amount": subtotal,
            "discount_amount": discount,
            "vat_amount": vat,
            "total_amount": total,
            "items": items,
            "confidence_score": confidence
        }