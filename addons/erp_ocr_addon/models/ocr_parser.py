import pytesseract
from PIL import Image
import base64
import io
import re

class OCRParser:

    @staticmethod
    def run_tesseract(base64_data):
        """Convert base64 → image → OCR Text"""
        try:
            image_data = base64.b64decode(base64_data)
            image = Image.open(io.BytesIO(image_data))

            text = pytesseract.image_to_string(image)
            return text

        except Exception as e:
            return f"OCR ERROR: {str(e)}"

    @staticmethod
    def extract_fields(text):
        """Very simple regex-based extraction for demo"""
        fields = {}

        # vendor name (first capital words)
        vendor_match = re.search(r'([A-Z][A-Za-z ]{3,})', text)
        fields["vendor_name"] = vendor_match.group(1).strip() if vendor_match else ""

        # total amount
        total_match = re.search(r'Total[: ]*([0-9,.]+)', text, re.IGNORECASE)
        fields["total_amount"] = float(total_match.group(1).replace(',', '')) if total_match else 0.0

        # vat
        vat_match = re.search(r'VAT[: ]*([0-9,.]+)', text, re.IGNORECASE)
        fields["vat_amount"] = float(vat_match.group(1).replace(',', '')) if vat_match else 0.0

        # date
        date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
        fields["invoice_date"] = date_match.group(1) if date_match else ""

        fields["confidence"] = 0.88  # dummy score

        return fields
