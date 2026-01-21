# -*- coding: utf-8 -*-
import re


class OCRParser:
    """
    Enterprise-grade OCR parser
    Supports:
    - Broken HTML tables (Typhoon OCR)
    - Thai + English invoices
    - Confidence + debug logs
    """

    # ======================================================
    # NORMALIZE RAW OCR TEXT (CRITICAL)
    # ======================================================
    @staticmethod
    def normalize(text: str) -> list:
        if not text:
            return []

        # Fix broken <tdXXX → <td>XXX
        text = re.sub(r"<td([^>])", r"<td>\1", text)
        text = re.sub(r"</td([^>])", r"</td>", text)

        # Fix <tr<td → <tr><td
        text = text.replace("<tr<td", "<tr><td")

        # Force line breaks
        text = text.replace("</td>", "</td>\n")
        text = text.replace("</tr>", "</tr>\n")

        # Remove table wrappers
        text = re.sub(r"</?table.*?>", "", text)

        # Normalize whitespace
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)

        return [l.strip() for l in text.splitlines() if l.strip()]

    # ======================================================
    # PARSE AMOUNT
    # ======================================================
    @staticmethod
    def parse_amount(text: str) -> float:
        m = re.search(r"[0-9,]+\.\d{2}", text)
        return float(m.group().replace(",", "")) if m else 0.0

    # ======================================================
    # NORMALIZE DATE (DD/MM/YYYY)
    # ======================================================
    @staticmethod
    def normalize_date(text: str):
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
        if not m:
            return None
        d, mth, y = m.groups()
        return f"{y}-{mth.zfill(2)}-{d.zfill(2)}"

    # ======================================================
    # PARSE ITEMS (SLIDING WINDOW)
    # ======================================================
    @staticmethod
    def parse_items(lines: list, log: list) -> list:
        items = []

        for i in range(len(lines) - 4):
            window = lines[i:i + 5]

            if (
                window[0].isdigit()
                and re.match(r"\d+(\.\d+)?", window[2])
                and re.match(r"\d+(\.\d+)?", window[3])
                and re.match(r"\d+(\.\d+)?", window[4])
            ):
                try:
                    item = {
                        "item_number": window[0],
                        "description": window[1],
                        "quantity": float(window[2]),
                        "unit_price": float(window[3]),
                        "line_total": float(window[4]),
                    }
                    items.append(item)
                    log.append(
                        f"[ITEM] {item['description']} | "
                        f"Qty={item['quantity']} | "
                        f"Unit={item['unit_price']} | "
                        f"Total={item['line_total']}"
                    )
                except Exception:
                    continue

        if items:
            log.append(f"[ITEMS] Parsed {len(items)} item(s)")
        else:
            log.append("[MISS] No item rows detected")

        return items

    # ======================================================
    # MAIN EXTRACTOR
    # ======================================================
    @staticmethod
    def extract_fields(raw_text: str) -> dict:
        log = []
        confidence = 0.0

        lines = OCRParser.normalize(raw_text)

        vendor = ""
        customer = ""
        tax_id = ""
        receipt_no = ""
        invoice_date = None

        # ---------------- HEADER ----------------
        for line in lines:
            l = line.lower()

            if not vendor and re.search(r"co\.?,?\s*ltd|บริษัท", line, re.I):
                vendor = line.strip()
                log.append(f"[HEADER] Vendor: {vendor}")
                confidence += 0.2

            if not customer and "customer name" in l:
                customer = line.split(":", 1)[-1].strip()
                log.append(f"[HEADER] Customer: {customer}")

            if not tax_id and "tax id" in l:
                m = re.search(r"\d{10,13}", line)
                if m:
                    tax_id = m.group()
                    log.append(f"[HEADER] Tax ID: {tax_id}")
                    confidence += 0.2

            if not receipt_no and "invoice" in l and "no" in l:
                receipt_no = line.split(":", 1)[-1].strip()
                log.append(f"[HEADER] Invoice No: {receipt_no}")

            if "date" in l:
                nd = OCRParser.normalize_date(line)
                if nd:
                    invoice_date = nd
                    log.append(f"[HEADER] Date: {nd}")
                    confidence += 0.1

        # ---------------- ITEMS ----------------
        items = OCRParser.parse_items(lines, log)
        if items:
            confidence += 0.2

        # ---------------- TOTALS ----------------
        subtotal = None
        discount = 0.0
        vat = 0.0
        total = None

        for line in lines:
            l = line.lower()

            if "total amount" in l and "vat" in l:
                total = OCRParser.parse_amount(line)
                log.append(f"[TOTALS] Total (Incl VAT): {total}")
                confidence += 0.2

            elif l.startswith("discount"):
                discount = OCRParser.parse_amount(line)
                log.append(f"[TOTALS] Discount: {discount}")

            elif "net amount after discount" in l:
                subtotal = OCRParser.parse_amount(line)
                log.append(f"[TOTALS] Net after discount: {subtotal}")

            elif "vat amount" in l:
                vat = OCRParser.parse_amount(line)
                log.append(f"[TOTALS] VAT: {vat}")
                confidence += 0.2

            elif "net amount (excluded vat)" in l and subtotal is None:
                subtotal = OCRParser.parse_amount(line)
                log.append(f"[TOTALS] Net excl VAT: {subtotal}")

        if subtotal and vat and total:
            if abs((subtotal + vat) - total) <= 1.0:
                log.append("[OK] Totals validated")
                confidence += 0.1
            else:
                log.append("[WARN] Totals mismatch")
                confidence -= 0.2

        confidence = max(0.0, min(1.0, confidence))
        log.append(f"[FINAL] Confidence Score = {round(confidence, 2)}")

        return {
            "vendor_name": vendor,
            "customer_name": customer,
            "tax_id": tax_id,
            "receipt_number": receipt_no,
            "invoice_date": invoice_date,
            "subtotal_amount": subtotal,
            "discount_amount": discount,
            "vat_amount": vat,
            "total_amount": total,
            "items": items,
            "confidence_score": round(confidence, 2),
            "extraction_log": "\n".join(log),
        }
