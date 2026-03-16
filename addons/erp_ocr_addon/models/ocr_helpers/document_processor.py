from .cleaners import clean_vendor_name, clean_text_field, normalize_phone
from .fallback_extractors import fallback_extract_customer_name, fallback_extract_customer_tax_id, fallback_extract_reference
import re


def process_document_data(raw_data):
    data = dict(raw_data)
    doc_type = data.get("doc_type", "invoice")
    # Clean vendor name
    data["vendor_name"] = clean_vendor_name(data.get("vendor_name"))

    # Clean customer name
    data["customer_name"] = clean_text_field(data.get("customer_name"))

    # Clean website
    data["vendor_website"] = clean_text_field(data.get("vendor_website"))
    data["vendor_phone"] = normalize_phone(data.get("vendor_phone"))
    # Clean tax ids
    data["vendor_tax_id"] = clean_text_field(data.get("vendor_tax_id"))
    data["customer_tax_id"] = clean_text_field(data.get("customer_tax_id"))

    # ==========================================
    # 🔥 ONLY FOR INVOICE (NO FALLBACK FOR RECEIPT)
    # ==========================================
    if doc_type != "receipt":

        # Discount fallback
        if not data.get("discount_amount"):
            raw_text = data.get("raw_text") or ""

            discount_keywords = [
                "ส่วนลด", "ลดราคา", "หักส่วนลด",
                "โปรโมชั่น", "โปรโมชัน", "Discount", "Promo"
            ]

            pattern = r"(?:%s)[^\n]*\n?\s*[-]?\s*([0-9]+\.[0-9]{2})" % "|".join(discount_keywords)

            m = re.search(pattern, raw_text, re.IGNORECASE)

            if m:
                try:
                    data["discount_amount"] = float(m.group(1))
                except Exception:
                    pass

        # Customer Tax
        if not data.get("customer_tax_id"):
            fallback_tax = fallback_extract_customer_tax_id(data)
            if fallback_tax:
                data["customer_tax_id"] = fallback_tax

        # Reference
        if not data.get("reference_number"):
            ref_fallback = fallback_extract_reference(data)
            if ref_fallback:
                data["reference_number"] = ref_fallback

        # Customer Name
        if not data.get("customer_name"):
            name = fallback_extract_customer_name(data.get("raw_text"))
            if name:
                data["customer_name"] = name
    return data