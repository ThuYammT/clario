# -*- coding: utf-8 -*-
import base64
import io
import re

import cv2
import numpy as np
from PIL import Image
import pytesseract


class OCRParser:
    """
    Universal OCR + parser for invoices/receipts.
    Uses:
      - OpenCV preprocessing
      - Tesseract OCR (eng+tha)
      - Heuristic extraction (works across many formats)
    """

    # =====================================================
    # 1) OCR with preprocessing
    # =====================================================
    @staticmethod
    def run_tesseract(base64_data):
        if not base64_data:
            return ""

        try:
            # Decode Odoo binary (base64)
            if isinstance(base64_data, str):
                image_bytes = base64.b64decode(base64_data)
            else:
                image_bytes = base64.b64decode(base64_data)

            pil_img = Image.open(io.BytesIO(image_bytes))

            # --- OpenCV preprocessing ---
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Upscale – Tesseract likes ~300dpi
            gray = cv2.resize(gray, None, fx=1.8, fy=1.8, interpolation=cv2.INTER_LINEAR)

            # Denoise
            gray = cv2.fastNlMeansDenoising(gray, h=30)

            # Threshold
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Sharpen
            kernel = np.array([[0, -1, 0],
                               [-1, 5, -1],
                               [0, -1, 0]])
            sharp = cv2.filter2D(thresh, -1, kernel)

            pre = Image.fromarray(sharp)

            text = pytesseract.image_to_string(
                pre,
                lang="eng+tha",
                config="--psm 6 --oem 3",
            )

            # Basic clean-up
            text = text.replace(" .", ".").replace(" ,", ",")

            # Fix broken numbers like "1699 48"
            text = OCRParser._merge_broken_numbers(text)

            return text or ""

        except Exception as e:
            return f"OCR ERROR: {str(e)}"

    # =====================================================
    # 2) Helpers: fixing & parsing numbers
    # =====================================================
    @staticmethod
    def _merge_broken_numbers(text):
        """
        Merge common OCR splits such as:
          1699 48  -> 1699.48
          1.798 39 -> 1798.39
        This runs BEFORE extraction.
        """
        # 1699 48 → 1699.48
        text = re.sub(r"(\d{1,6})\s+(\d{2})", r"\1.\2", text)

        # 1.798 39 → 1798.39
        text = re.sub(r"(\d)[\.,](\d{3})\s+(\d{2})", r"\1\2.\3", text)

        return text

    @staticmethod
    def _clean_number(raw):
        """
        Normalize OCR number string to float.
        Handles commas, spaces, common OCR mistakes.
        """
        if not raw:
            return 0.0
        s = raw.strip()

        # replace common OCR letter→digit mistakes
        s = s.replace("O", "0").replace("S", "5")

        # remove spaces
        s = s.replace(" ", "")

        # handle comma/point as thousands/decimal
        # case 1: both '.' and ',' present
        if "," in s and "." in s:
            # assume last separator is decimal
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_comma > last_dot:
                # comma as decimal
                s = s.replace(".", "")
                s = s.replace(",", ".")
            else:
                # dot as decimal
                s = s.replace(",", "")
        else:
            # only one type of separator
            if "," in s:
                # if exactly one comma and 2 digits after it, treat as decimal
                parts = s.split(",")
                if len(parts) == 2 and len(parts[1]) == 2:
                    s = s.replace(",", ".")
                else:
                    s = s.replace(",", "")

        try:
            return float(s)
        except Exception:
            return 0.0

    @staticmethod
    def _extract_numbers_from_line(line):
        """
        Return list of float numbers that look like money from a line.
        """
        nums = []
        # match optional currency + number
        for m in re.finditer(r"[$฿€£]?\s*([0-9][0-9 ,\.]*)", line):
            val = OCRParser._clean_number(m.group(1))
            if val > 0:
                nums.append(val)
        return nums

    # =====================================================
    # 3) Main extraction
    # =====================================================
    @staticmethod
    def extract_fields(text):
        """
        Universal field extraction.
        Returns dict with:
          vendor_name, total_amount, vat_amount, invoice_date_raw, confidence
        """
        fields = {
            "vendor_name": "",
            "total_amount": 0.0,
            "vat_amount": 0.0,
            "invoice_date_raw": "",
            "confidence": 0.0,
        }

        if not text or text.startswith("OCR ERROR:"):
            return fields

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        n_lines = len(lines)

        # ------------------------------------------
        # A) Vendor name – from top non-numeric lines
        # ------------------------------------------
        vendor = ""
        stop_keywords = ("invoice", "tax invoice", "receipt", "bill", "statement")
        for line in lines[:12]:
            lower = line.lower()
            if any(k in lower for k in stop_keywords):
                break

            # skip if too many digits
            if len(re.findall(r"\d", line)) > 4:
                continue

            if re.match(r"^[A-Za-zก-ฮเ-๙0-9 .,&\-]{3,}$", line):
                vendor = line
                break

        fields["vendor_name"] = vendor

        # ------------------------------------------
        # B) Date – look for first proper date pattern
        # ------------------------------------------
        date_match = re.search(
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
            text,
        )
        fields["invoice_date_raw"] = date_match.group(1) if date_match else ""

        # ------------------------------------------
        # C) Collect all money candidates by line
        # ------------------------------------------
        money_candidates = []  # list of dicts: {value, line_idx, label, line}
        for idx, line in enumerate(lines):
            lower = line.lower()
            nums = OCRParser._extract_numbers_from_line(line)
            if not nums:
                continue

            label = "other"
            if "subtotal" in lower:
                label = "subtotal"
            elif "discount" in lower:
                label = "discount"
            elif any(k in lower for k in ("vat", "tax", "gst")):
                label = "tax"
            elif any(k in lower for k in ("amount due", "balance due", "total")):
                # careful: avoid counting "subtotal" here
                if "subtotal" not in lower:
                    label = "total"

            for v in nums:
                money_candidates.append(
                    {
                        "value": v,
                        "line_idx": idx,
                        "label": label,
                        "line": line,
                    }
                )

        # ------------------------------------------
        # D) TOTAL amount heuristic
        # ------------------------------------------
        total_val = 0.0

        # 1) Prefer explicit 'amount due' / 'balance due' / 'total' lines
        explicit_totals = [
            c for c in money_candidates if c["label"] == "total"
        ]
        if explicit_totals:
            # If multiple, pick the one closest to bottom
            explicit_totals.sort(key=lambda c: (c["line_idx"], -c["value"]))
            total_val = explicit_totals[-1]["value"]

        # 2) Fallback: pick the largest amount in bottom 40% as total
        if total_val == 0.0 and money_candidates:
            threshold = int(n_lines * 0.6)
            bottom_candidates = [
                c for c in money_candidates if c["line_idx"] >= threshold
            ] or money_candidates
            total_val = max(c["value"] for c in bottom_candidates)

        fields["total_amount"] = total_val

        # ------------------------------------------
        # E) VAT / Tax amount heuristic
        # ------------------------------------------
        vat_val = 0.0

        # 1) direct 'tax', 'vat', 'gst' lines
        tax_candidates = [c for c in money_candidates if c["label"] == "tax"]
        if tax_candidates:
            # Pick the one closest to total in vertical distance
            if total_val > 0:
                tax_candidates.sort(
                    key=lambda c: abs(c["line_idx"] - OCRParser._closest_line_to_value(money_candidates, total_val))
                )
            vat_val = tax_candidates[0]["value"]

        # 2) ratio-based guess (5–20% of total)
        if vat_val == 0.0 and total_val > 0:
            near_ratio = [
                c for c in money_candidates
                if 0.03 * total_val <= c["value"] <= 0.25 * total_val
                and c["label"] not in ("discount", "subtotal")
            ]
            if near_ratio:
                # choose one whose line has 'tax' or 'vat' if possible
                near_ratio.sort(key=lambda c: (
                    not any(k in c["line"].lower() for k in ("vat", "tax", "gst")),
                    -c["value"],
                ))
                vat_val = near_ratio[0]["value"]

        fields["vat_amount"] = vat_val

        # ------------------------------------------
        # F) Confidence score
        # ------------------------------------------
        score = 0.0
        if vendor:
            score += 0.25
        if total_val > 0:
            score += 0.45
        if vat_val > 0:
            score += 0.20
        if fields["invoice_date_raw"]:
            score += 0.10

        fields["confidence"] = round(min(score, 1.0), 2)

        return fields

    # -------------------------------------------------
    # Helper: find line index closest to a numeric value
    # -------------------------------------------------
    @staticmethod
    def _closest_line_to_value(candidates, value):
        """
        For a given numeric value, return the line index of
        the candidate with that value (or closest).
        """
        if not candidates:
            return 0
        best = min(
            candidates,
            key=lambda c: abs(c["value"] - value),
        )
        return best["line_idx"]
