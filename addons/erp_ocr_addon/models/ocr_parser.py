# -*- coding: utf-8 -*-
import re


class OCRParser:
    """
    Generic, layout-driven invoice/receipt parser.
    Works across languages, vendors, and formats.
    """

    # =========================
    # TEXT NORMALIZATION
    # =========================
    @staticmethod
    def normalize(text):
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    # =========================
    # ZONE SPLITTING (POSITIONAL)
    # =========================
    @staticmethod
    def split_zones(lines):
        """
        Split document into semantic zones by vertical position.
        """
        n = len(lines)
        if n == 0:
            return [], [], []

        top = lines[: int(n * 0.35)]
        middle = lines[int(n * 0.35): int(n * 0.70)]
        bottom = lines[int(n * 0.70):]

        return top, middle, bottom

    # =========================
    # HELPER: FIND NEAREST VALUE
    # =========================
    @staticmethod
    def next_value(lines, idx):
        """
        Return the nearest meaningful value line after a label.
        """
        for j in range(idx + 1, min(idx + 6, len(lines))):
            if re.search(r"[0-9A-Za-zก-๙]", lines[j]):
                return lines[j]
        return ""

    # =========================
    # HELPER: PARSE FLOAT
    # =========================
    @staticmethod
    def parse_amount(text):
        try:
            return float(text.replace(",", ""))
        except Exception:
            return 0.0

    # =========================
    # MAIN EXTRACTION
    # =========================
    @staticmethod
    def extract_fields(raw_text):
        text = OCRParser.normalize(raw_text)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        top, middle, bottom = OCRParser.split_zones(lines)

        fields = {
            # Header
            "vendor_name": "",
            "customer_name": "",
            "tax_id": "",
            "invoice_number": "",
            "invoice_date": "",

            # Amounts
            "subtotal_amount": 0.0,
            "discount_amount": 0.0,
            "vat_amount": 0.0,
            "total_amount": 0.0,
        }

        # =========================
        # TOP ZONE — HEADER
        # =========================
        for i, line in enumerate(top):

            # Vendor name heuristic:
            # First long textual line (not numeric)
            if not fields["vendor_name"]:
                if len(line) > 4 and not re.search(r"\d{4,}", line):
                    fields["vendor_name"] = line

            # Tax ID (numeric dominant)
            if re.search(r"(tax|vat|ภาษี)", line, re.I):
                candidate = OCRParser.next_value(top, i)
                m = re.search(r"\d{10,13}", candidate)
                if m:
                    fields["tax_id"] = m.group()

            # Invoice / receipt number
            if re.search(r"(invoice|receipt|no\.|เลขที่)", line, re.I):
                fields["invoice_number"] = OCRParser.next_value(top, i)

            # Date
            if re.search(r"(date|วันที่)", line, re.I):
                candidate = OCRParser.next_value(top, i)
                m = re.search(r"\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}", candidate)
                if m:
                    fields["invoice_date"] = m.group()

            # Customer name
            if re.search(r"(customer|ลูกค้า)", line, re.I):
                fields["customer_name"] = OCRParser.next_value(top, i)

        # =========================
        # BOTTOM ZONE — TOTALS
        # =========================
        for i, line in enumerate(bottom):

            # TOTAL (largest / final amount)
            if re.search(r"(total|grand|รวม)", line, re.I):
                val = OCRParser.next_value(bottom, i)
                fields["total_amount"] = OCRParser.parse_amount(val)

            # VAT
            if re.search(r"(vat|ภาษี)", line, re.I):
                val = OCRParser.next_value(bottom, i)
                fields["vat_amount"] = OCRParser.parse_amount(val)

            # Discount
            if re.search(r"(discount|ส่วนลด)", line, re.I):
                val = OCRParser.next_value(bottom, i)
                fields["discount_amount"] = OCRParser.parse_amount(val)

            # Subtotal / Net
            if re.search(r"(net|subtotal|ก่อนภาษี)", line, re.I):
                val = OCRParser.next_value(bottom, i)
                fields["subtotal_amount"] = OCRParser.parse_amount(val)

        return fields
