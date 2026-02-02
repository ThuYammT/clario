# -*- coding: utf-8 -*-
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import logging

_logger = logging.getLogger(__name__)

class AzureInvoiceService:
    """
    Advanced Wrapper for Azure Document Intelligence
    Based on 'Friend's Code' capabilities:
    - Smart Address Formatting
    - Multiple Candidate Search (for Tax IDs/Phones)
    - Currency Extraction
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
        except:
            pass

        if not result.documents:
            return {"raw_text": raw_text or ""}

        invoice = result.documents[0]
        fields = invoice.fields or {}
        log = []

        # --- Helper Functions ---
        def fget(name):
            return fields.get(name)

        def get_str(name):
            f = fget(name)
            return f.value_string if f else None

        def get_date(name):
            f = fget(name)
            return f.value_date if f else None

        def get_currency(name):
            """Returns (amount, currency_code)"""
            f = fget(name)
            if not f or not f.value_currency:
                return (None, None)
            cur = f.value_currency
            return (cur.amount, getattr(cur, "currency_code", None))

        def get_first_str(candidates):
            """Searches a list of keys until one returns a value"""
            for key in candidates:
                v = get_str(key)
                if v: return v
            return None

        def format_address(field_name):
            """Smart Address Formatting (Friend's Logic)"""
            f = fget(field_name)
            if not f: return None
            
            # If Azure gives us a structured address object
            if f.value_address:
                addr = f.value_address
                parts = []
                # Thai specific ordering preference
                if getattr(addr, "house_number", None): parts.append(f"เลขที่ {addr.house_number}")
                if getattr(addr, "road", None): parts.append(addr.road)
                if getattr(addr, "city_district", None): parts.append(f"เขต{addr.city_district}")
                if getattr(addr, "city", None): parts.append(addr.city)
                if getattr(addr, "postal_code", None): parts.append(addr.postal_code)
                if getattr(addr, "country_region", None): parts.append(addr.country_region)
                
                joined = " ".join([p for p in parts if p]).strip()
                if joined: return joined

            # Fallback to string representation
            return f.content if f.content else None

        # --- EXTRACTION START ---

        # 1. Parties & IDs (Using 'get_first_str' to catch variations)
        vendor_name = get_str("VendorName")
        customer_name = get_str("CustomerName")
        
        # Friend's code looks for multiple keys for Tax IDs
        vendor_tax_id = get_first_str(["VendorTaxId", "TaxId", "VendorVATNumber"])
        customer_tax_id = get_first_str(["CustomerTaxId", "CustomerVATNumber"])

        # Contact Info (New features)
        vendor_phone = get_first_str(["VendorPhoneNumber", "VendorPhone", "PhoneNumber"])
        customer_phone = get_first_str(["CustomerPhoneNumber", "CustomerPhone"])
        vendor_website = get_first_str(["VendorWebsite", "Website"])

        # Addresses
        vendor_address = format_address("VendorAddress")
        customer_address = format_address("CustomerAddress")

        # Document Info
        document_number = get_first_str(["InvoiceId", "InvoiceNumber", "ReceiptNumber", "ReferenceNumber"])
        reference_number = get_first_str(["PurchaseOrder", "Reference", "ReferenceNumber"])
        invoice_date = get_date("InvoiceDate") or get_date("Date")
        due_date = get_date("DueDate")
        payment_terms = get_str("PaymentTerm") or get_str("PaymentTerms")

        # 2. Financials & Currency
        subtotal, c1 = get_currency("SubTotal")
        discount, c2 = get_currency("TotalDiscount")
        vat, c3 = get_currency("TotalTax")
        total, c4 = get_currency("InvoiceTotal")
        
        # Try to find a valid currency code
        currency_code = c4 or c3 or c2 or c1

        # 3. Smart Totals Calculation (Friend's Logic)
        # Often receipts include VAT in the subtotal. We try to find the 'Net' amount.
        vat_base_amount = None
        # Try to read 'TotalNet' from Azure directly
        net_field = get_currency("TotalNet")
        if net_field[0] is not None:
            vat_base_amount = net_field[0]
        # Or calculate it: Total - VAT
        elif total is not None and vat is not None:
            vat_base_amount = round(float(total) - float(vat), 2)
        
        # 4. Line Items
        items = []
        if fget("Items") and fget("Items").value_array:
            for item in fget("Items").value_array:
                obj = item.value_object
                if not obj: continue
                
                # Safe Extraction helpers for lines
                def l_str(k): return obj.get(k).value_string if obj.get(k) else ""
                def l_num(k): return obj.get(k).value_number if obj.get(k) else 1.0
                def l_money(k): return obj.get(k).value_currency.amount if obj.get(k) and obj.get(k).value_currency else 0.0

                items.append({
                    "description": l_str("Description"),
                    "product_code": l_str("ProductCode"),
                    "quantity": l_num("Quantity"),
                    "unit_price": l_money("UnitPrice"),
                    "amount": l_money("Amount") or l_money("Tax") # Fallback
                })

        confidence = invoice.confidence if hasattr(invoice, "confidence") else 0.9

        # Return standardized dict
        return {
            # Meta
            "raw_text": raw_text,
            "confidence_score": confidence,
            "currency_code": currency_code,

            # Header
            "invoice_id": document_number,
            "reference_number": reference_number,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "payment_terms": payment_terms,

            # Vendor
            "vendor_name": vendor_name,
            "vendor_tax_id": vendor_tax_id,
            "vendor_address": vendor_address,
            "vendor_phone": vendor_phone,
            "vendor_website": vendor_website,

            # Customer
            "customer_name": customer_name,
            "customer_tax_id": customer_tax_id,
            "customer_address": customer_address,
            "customer_phone": customer_phone,

            # Totals
            "subtotal_amount": subtotal,
            "discount_amount": discount,
            "vat_amount": vat,
            "total_amount": total,
            "vat_base_amount": vat_base_amount, # The "Smart" calculation

            "items": items
        }