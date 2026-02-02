# -*- coding: utf-8 -*-
"""
Semantic multilingual parser (TH + EN) for invoices/receipts.

Enterprise design:
- Parser owns "meaning" (document number, totals, parties, etc.).
- OCR engine layer (azure.py) only extracts raw outputs.
- This parser merges:
    (1) structured fields from engine
    (2) raw OCR text
    (3) raw items array
  into a stable, UI-ready dictionary used by ocr.document.

Goal:
- "More is ok. Less is not ok."
- Extract as many enterprise fields as realistically possible,
  with safe fallbacks and clear extraction logs.
"""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional


class OCRParser:
    # -------------------------
    # Text normalization
    # -------------------------
    @staticmethod
    def normalize_lines(text: str) -> List[str]:
        """
        Normalize OCR text into clean lines.
        Handles cases where OCR returns HTML-ish table fragments or weird whitespace.
        """
        if not text:
            return []
        text = re.sub(r"</?table.*?>", "", text, flags=re.I)
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return [l.strip() for l in text.splitlines() if l.strip()]

    # -------------------------
    # Amount parsing helpers
    # -------------------------
    _AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))(?!\d)")

    @staticmethod
    def parse_amount(text: str) -> Optional[float]:
        if not text:
            return None
        m = OCRParser._AMOUNT_RE.search(text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            return None

    # -------------------------
    # Date parsing helpers
    # -------------------------
    _DATE_DMY_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})")
    _DATE_YMD_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
    _DATE_TEXT_EN = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b", re.I)

    @staticmethod
    def normalize_date(text: str) -> Optional[str]:
        """
        Return YYYY-MM-DD when possible.
        Supports:
        - dd/mm/yyyy, dd-mm-yyyy
        - yyyy/mm/dd
        - Thai buddhist years (>= 2400) -> convert to CE by -543
        """
        if not text:
            return None
        text = text.strip()

        m = OCRParser._DATE_YMD_RE.search(text)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{str(mo).zfill(2)}-{str(d).zfill(2)}"

        m = OCRParser._DATE_DMY_RE.search(text)
        if m:
            d, mo, y = m.groups()
            y_int = int(y)
            if y_int < 100:
                y_int = 2000 + y_int
            if y_int >= 2400:
                y_int -= 543
            return f"{y_int}-{str(mo).zfill(2)}-{str(d).zfill(2)}"

        if OCRParser._DATE_TEXT_EN.search(text):
            m2 = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", text)
            if m2:
                d, mon, y = m2.groups()
                mon_map = {
                    "jan": 1, "january": 1,
                    "feb": 2, "february": 2,
                    "mar": 3, "march": 3,
                    "apr": 4, "april": 4,
                    "may": 5,
                    "jun": 6, "june": 6,
                    "jul": 7, "july": 7,
                    "aug": 8, "august": 8,
                    "sep": 9, "sept": 9, "september": 9,
                    "oct": 10, "october": 10,
                    "nov": 11, "november": 11,
                    "dec": 12, "december": 12,
                }
                key = mon.lower()
                mo = mon_map.get(key, None) or mon_map.get(key[:4], None) or mon_map.get(key[:3], None)
                if mo:
                    return f"{y}-{str(mo).zfill(2)}-{str(int(d)).zfill(2)}"

        return None

    # -------------------------
    # Semantic label sets (TH + EN)
    # -------------------------
    LABELS = {
        "DOCUMENT_NUMBER": [
            r"เลขที่", r"เลข\s*ที่", r"ใบกำกับภาษี\s*เลขที่", r"เลขที่เอกสาร",
            r"\b(invoice|receipt|tax\s*invoice)\s*(no|number)\b", r"\bno\.?\b", r"\bdoc(?:ument)?\s*(no|number)\b",
        ],
        "DOCUMENT_DATE": [
            r"วันที่", r"วันที่ออก", r"วัน/เดือน/ปี", r"\bdate\b", r"\bissued\s*date\b", r"\btransaction\s*date\b",
        ],
        "DUE_DATE": [
            r"กำหนดชำระ", r"วันครบกำหนด", r"\bdue\s*date\b",
        ],
        "SUBTOTAL_EXCL_TAX": [
            r"ยอดเงินก่อนภาษี", r"ก่อนภาษี", r"มูลค่าสินค้า",
            r"\bsub\s*total\b", r"\bsubtotal\b", r"\bexclude\s*tax\b", r"\bamount\s*before\s*tax\b",
        ],
        "DISCOUNT": [r"ส่วนลด", r"\bdiscount\b"],
        "VAT": [r"ภาษีมูลค่าเพิ่ม", r"\bvalue\s*added\s*tax\b", r"\bvat\b"],
        "GRAND_TOTAL": [
            r"จำนวนเงินรวมทั้งสิ้น", r"ยอดรวมสุทธิ", r"ยอดรวม",
            r"\bgrand\s*total\b", r"\btotal\s*amount\b", r"\btotal\b",
        ],
        "AMOUNT_IN_WORDS": [
            r"จำนวนเงิน\s*\(ตัวอักษร\)", r"ตัวอักษร", r"\bamount\s*in\s*words\b",
        ],
        "CUSTOMER": [r"ลูกค้า", r"\bcustomer\b", r"\bbill\s*to\b", r"\bship\s*to\b"],
        "REFERENCE_NUMBER": [r"อ้างอิง", r"\breference\b", r"\bpo\s*no\b", r"\bpurchase\s*order\b"],
    }

    # -------------------------
    # Structured field helpers
    # -------------------------
    @staticmethod
    def _sf_get(structured_fields: Dict[str, Any], key: str) -> Optional[Any]:
        e = structured_fields.get(key) if structured_fields else None
        if not e:
            return None
        for k in ("value_string", "value_number", "value_date"):
            if k in e and e[k] not in (None, ""):
                return e[k]
        if "value_currency" in e and e["value_currency"] and e["value_currency"].get("amount") is not None:
            return e["value_currency"]["amount"]
        if "display_address" in e and e["display_address"]:
            return e["display_address"]
        return e.get("content")

    @staticmethod
    def _pick_best_text(candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        c = str(candidate).strip()
        return c if c else None

    # -------------------------
    # Core semantic extractors (from raw text)
    # -------------------------
    @staticmethod
    def _match_after_label(lines: List[str], label_patterns: List[str], value_regex: str, max_lookahead: int = 1) -> Optional[str]:
        if not lines:
            return None
        value_re = re.compile(value_regex, re.I)
        for i, line in enumerate(lines):
            for lp in label_patterns:
                if re.search(lp, line, re.I):
                    m = value_re.search(line)
                    if m:
                        return m.group(1).strip()
                    for j in range(1, max_lookahead + 1):
                        if i + j < len(lines):
                            m2 = value_re.search(lines[i + j])
                            if m2:
                                return m2.group(1).strip()
        return None

    @staticmethod
    def _find_tax_id(lines: List[str]) -> Optional[str]:
        for line in lines:
            if re.search(r"(เลขประจำตัวผู้เสียภาษี|tax\s*id|vat\s*id)", line, re.I):
                m = re.search(r"(\d{10,13})", line)
                if m:
                    return m.group(1)
        for line in lines[:30]:
            m = re.search(r"\b(\d{13})\b", line)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _find_document_number(lines: List[str]) -> Optional[str]:
        val = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["DOCUMENT_NUMBER"],
            r"(?:เลขที่|no\.?|number|invoice\s*no|receipt\s*no|tax\s*invoice\s*no)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{4,})",
            max_lookahead=2,
        )
        if val:
            return val
        for line in lines[:25]:
            m = re.search(r"\b([A-Z]{1,5}[-/]\d{2,}[-/]\d{2,}|[A-Z0-9]{6,}[-/][A-Z0-9]{2,}|\d{6,})\b", line)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _find_document_date(lines: List[str]) -> Optional[str]:
        raw = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["DOCUMENT_DATE"],
            r"(?:date|วันที่)\s*[:\-]?\s*([0-9]{1,4}[/-][0-9]{1,2}[/-][0-9]{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
            max_lookahead=2,
        )
        if raw:
            return OCRParser.normalize_date(raw)
        for line in lines[:25]:
            nd = OCRParser.normalize_date(line)
            if nd:
                return nd
        return None

    @staticmethod
    def _find_due_date(lines: List[str]) -> Optional[str]:
        raw = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["DUE_DATE"],
            r"(?:due\s*date|กำหนดชำระ|วันครบกำหนด)\s*[:\-]?\s*([0-9]{1,4}[/-][0-9]{1,2}[/-][0-9]{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
            max_lookahead=2,
        )
        return OCRParser.normalize_date(raw) if raw else None

    @staticmethod
    def _find_reference(lines: List[str]) -> Optional[str]:
        raw = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["REFERENCE_NUMBER"],
            r"(?:reference|po\s*no|purchase\s*order|อ้างอิง)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{3,})",
            max_lookahead=2,
        )
        return raw.strip() if raw else None

    @staticmethod
    def _find_amount_by_labels(lines: List[str], label_patterns: List[str]) -> Optional[float]:
        for i, line in enumerate(lines):
            if any(re.search(lp, line, re.I) for lp in label_patterns):
                amt = OCRParser.parse_amount(line)
                if amt is not None:
                    return amt
                if i + 1 < len(lines):
                    amt2 = OCRParser.parse_amount(lines[i + 1])
                    if amt2 is not None:
                        return amt2
        return None

    @staticmethod
    def _find_vat_rate(lines: List[str]) -> Optional[float]:
        for line in lines:
            if re.search(r"\bvat\b|ภาษีมูลค่าเพิ่ม", line, re.I):
                m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", line)
                if m:
                    try:
                        return float(m.group(1))
                    except Exception:
                        pass
        return None

    @staticmethod
    def _guess_vendor_name(lines: List[str]) -> Optional[str]:
        for line in lines[:20]:
            if re.search(r"บริษัท", line):
                return line.strip()
            if re.search(r"\b(co\.|ltd\.|limited|company)\b", line, re.I):
                return line.strip()
        return None

    @staticmethod
    def _guess_customer_name(lines: List[str]) -> Optional[str]:
        val = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["CUSTOMER"],
            r"(?:customer|bill\s*to|ลูกค้า)\s*[:\-]?\s*(.+)$",
            max_lookahead=1,
        )
        if val:
            return val.strip()
        for i, line in enumerate(lines):
            if re.search(r"(customer|bill\s*to|ลูกค้า)", line, re.I):
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt and len(nxt) >= 3:
                        return nxt
        return None

    # -------------------------
    # Main merge API used by azure.py
    # -------------------------
    @staticmethod
    def from_engine_raw(
        raw_text: str,
        structured_fields: Dict[str, Any],
        items: List[Dict[str, Any]],
        engine_confidence: float,
        doc_type: str = "invoice",
    ) -> Dict[str, Any]:
        log: List[str] = []
        lines = OCRParser.normalize_lines(raw_text)

        # Structured candidates
        vendor_name_sf = OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "VendorName"))
        customer_name_sf = OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "CustomerName"))
        tax_id_sf = (
            OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "VendorTaxId"))
            or OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "TaxId"))
        )
        vendor_address_sf = OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "VendorAddress"))
        doc_no_sf = (
            OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "InvoiceId"))
            or OCRParser._pick_best_text(OCRParser._sf_get(structured_fields, "ReceiptNumber"))
        )
        doc_date_sf = OCRParser._sf_get(structured_fields, "InvoiceDate") or OCRParser._sf_get(structured_fields, "TransactionDate")

        subtotal_sf = OCRParser._sf_get(structured_fields, "SubTotal")
        discount_sf = OCRParser._sf_get(structured_fields, "TotalDiscount") or OCRParser._sf_get(structured_fields, "Discount")
        vat_sf = OCRParser._sf_get(structured_fields, "TotalTax") or OCRParser._sf_get(structured_fields, "Tax")
        total_sf = OCRParser._sf_get(structured_fields, "InvoiceTotal") or OCRParser._sf_get(structured_fields, "Total")

        # Text candidates
        vendor_name_tx = OCRParser._guess_vendor_name(lines)
        customer_name_tx = OCRParser._guess_customer_name(lines)
        tax_id_tx = OCRParser._find_tax_id(lines)
        doc_no_tx = OCRParser._find_document_number(lines)
        doc_date_tx = OCRParser._find_document_date(lines)
        due_date_tx = OCRParser._find_due_date(lines)
        ref_tx = OCRParser._find_reference(lines)

        subtotal_tx = OCRParser._find_amount_by_labels(lines, OCRParser.LABELS["SUBTOTAL_EXCL_TAX"])
        discount_tx = OCRParser._find_amount_by_labels(lines, OCRParser.LABELS["DISCOUNT"])
        vat_amt_tx = OCRParser._find_amount_by_labels(lines, OCRParser.LABELS["VAT"])
        total_tx = OCRParser._find_amount_by_labels(lines, OCRParser.LABELS["GRAND_TOTAL"])
        vat_rate_tx = OCRParser._find_vat_rate(lines)

        amount_words_tx = OCRParser._match_after_label(
            lines,
            OCRParser.LABELS["AMOUNT_IN_WORDS"],
            r"(?:ตัวอักษร|amount\s*in\s*words)\s*[:\-]?\s*(.+)$",
            max_lookahead=2,
        )

        vendor_name = vendor_name_sf or vendor_name_tx
        customer_name = customer_name_sf or customer_name_tx
        vendor_tax_id = tax_id_sf or tax_id_tx
        doc_no = doc_no_sf or doc_no_tx

        doc_date = None
        if doc_date_sf:
            doc_date = str(doc_date_sf)
        if not doc_date:
            doc_date = doc_date_tx

        def to_f(v) -> Optional[float]:
            if v is None or v == "":
                return None
            try:
                return float(v)
            except Exception:
                return None

        subtotal = to_f(subtotal_sf) if subtotal_sf is not None else subtotal_tx
        discount = to_f(discount_sf) if discount_sf is not None else discount_tx
        vat_amount = to_f(vat_sf) if vat_sf is not None else vat_amt_tx
        total_amount = to_f(total_sf) if total_sf is not None else total_tx

        if total_amount is None and subtotal is not None:
            computed = subtotal + (vat_amount or 0.0) - (discount or 0.0)
            total_amount = round(computed, 2)
            log.append(f"[TOTAL] Computed total_amount={total_amount} from subtotal/vat/discount")

        key_hits = 0
        for v in (vendor_name, vendor_tax_id, doc_no, doc_date, total_amount):
            if v:
                key_hits += 1
        base = float(engine_confidence or 0.0)
        conf = min(1.0, max(0.0, base * 0.8 + (key_hits / 5.0) * 0.2))

        if vendor_name:
            log.append(f"[PARTY] Seller/Vendor: {vendor_name}")
        if customer_name:
            log.append(f"[PARTY] Customer: {customer_name}")
        if vendor_tax_id:
            log.append(f"[ID] Tax ID: {vendor_tax_id}")
        if doc_no:
            log.append(f"[DOC] Document No: {doc_no}")
        if doc_date:
            log.append(f"[DOC] Document Date: {doc_date}")
        if due_date_tx:
            log.append(f"[DOC] Due Date: {due_date_tx}")
        if ref_tx:
            log.append(f"[DOC] Reference: {ref_tx}")

        if subtotal is not None:
            log.append(f"[AMT] Subtotal (excl tax): {subtotal}")
        if discount is not None:
            log.append(f"[AMT] Discount: {discount}")
        if vat_rate_tx is not None:
            log.append(f"[AMT] VAT rate: {vat_rate_tx}%")
        if vat_amount is not None:
            log.append(f"[AMT] VAT amount: {vat_amount}")
        if total_amount is not None:
            log.append(f"[AMT] Grand total: {total_amount}")

        if vendor_address_sf:
            log.append("[ADDR] Vendor address extracted from structured fields")
        if amount_words_tx:
            log.append("[AMT] Amount in words extracted")

        semantic_doc_type = doc_type
        if re.search(r"(tax\s*invoice|ใบกำกับภาษี)", raw_text or "", re.I) and re.search(r"(receipt|ใบเสร็จ)", raw_text or "", re.I):
            semantic_doc_type = "tax_invoice_receipt"
            log.append("[TYPE] Detected hybrid document: Tax Invoice + Receipt")

        return {
            "vendor_name": vendor_name,
            "customer_name": customer_name,
            "vendor_tax_id": vendor_tax_id,
            "tax_id": vendor_tax_id,
            "vendor_address": vendor_address_sf,

            "document_number": doc_no,
            "document_date": doc_date,
            "due_date": due_date_tx,
            "reference_number": ref_tx,

            "invoice_date": doc_date if doc_type == "invoice" else None,
            "receipt_date": doc_date if doc_type == "receipt" else None,
            "receipt_number": doc_no if doc_type == "receipt" else None,

            "subtotal_amount": subtotal,
            "discount_amount": discount if discount is not None else 0.0,
            "vat_percent": vat_rate_tx if vat_rate_tx is not None else None,
            "vat_amount": vat_amount,
            "total_amount": total_amount,

            "items": items or [],

            "semantic_doc_type": semantic_doc_type,
            "amount_in_words": amount_words_tx.strip() if amount_words_tx else None,

            "confidence_score": round(conf, 4),
            "extraction_log": "\n".join(log) if log else "[PARSER] No semantic fields matched",
        }
