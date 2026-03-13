import re

def fallback_extract_customer_tax_id(data):
    if data.get("customer_tax_id"):
        return data.get("customer_tax_id")

    raw_text = data.get("raw_text") or ""
    vendor_tax = data.get("vendor_tax_id")

    match = re.search(
        r"Customer\s*ID\s*[:\-]?\s*\n?\s*(\d{13})",
        raw_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    match = re.search(
        r"ลูกค้า.*?(?:Tax\s*ID|เลขประจำตัวผู้เสียภาษี).*?(\d{13})",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )

    if match:
        val = match.group(1)
        if val != vendor_tax:
            return val

    candidates = re.findall(r"\b\d{13}\b", raw_text)

    for num in candidates:
        if num != vendor_tax:
            return num

    return None


def fallback_extract_reference(data):
    raw_text = data.get("raw_text") or ""

    invoice_id = data.get("invoice_id")
    vendor_phone = data.get("vendor_phone")
    vendor_tax = data.get("vendor_tax_id")

    patterns = [
        r"Ref\s*ABB\.?\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"ABB\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Ref\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"Reference\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"เลขที่อ้างอิง\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"เลขอ้างอิง\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"เลขที่คำสั่งซื้อ\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"เลขที่ใบกำกับ\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
    ]

    for p in patterns:
        m = re.search(p, raw_text, re.IGNORECASE)

        if m:
            ref = m.group(1).strip()

            if ref and ref not in [invoice_id, vendor_phone, vendor_tax]:
                return ref

    return None