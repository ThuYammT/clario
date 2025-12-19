# -*- coding: utf-8 -*-
import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .ocr_parser import OCRParser

# ======================================================
# 🔒 GLOBAL SINGLETON OCR (CRITICAL FIX)
# ======================================================
_PADDLE_OCR = None


def get_paddle_ocr():
    """
    Initialize PaddleOCR ONLY ONCE per Odoo worker
    to avoid memory exhaustion & model export crashes.
    """
    global _PADDLE_OCR
    if _PADDLE_OCR is None:
        from paddleocr import PaddleOCR
        _PADDLE_OCR = PaddleOCR(
            lang="en",
            use_gpu=False,
            use_angle_cls=False,

            # 🔥 MEMORY SAFE SETTINGS
            rec_batch_num=1,
            det_limit_side_len=640,
            enable_mkldnn=False,
            cpu_threads=1,

            show_log=False,
        )
    return _PADDLE_OCR


# ======================================================
# OCR DOCUMENT MODEL
# ======================================================
class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document"
    _order = "create_date desc"

    # =========================
    # BASIC
    # =========================
    name = fields.Char(required=True)
    file = fields.Binary(string="File", attachment=True, required=True)

    doc_type = fields.Selection(
        [("invoice", "Invoice"), ("receipt", "Receipt")],
        default="invoice",
        required=True,
    )

    upload_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        readonly=True,
    )

    status = fields.Selection(
        [
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("error", "Error"),
        ],
        default="uploaded",
    )

    progress = fields.Integer(default=0)

    # =========================
    # HEADER / PARTIES
    # =========================
    customer_name = fields.Char()
    supplier_name = fields.Char()
    vendor_name = fields.Char()
    seller_id = fields.Char()
    company_issued = fields.Char()
    tax_id = fields.Char()
    vendor_address = fields.Text()
    vendor_phone = fields.Char()

    # =========================
    # DOCUMENT INFO
    # =========================
    invoice_date = fields.Date()
    receipt_date = fields.Date()
    receipt_number = fields.Char()
    reference_number = fields.Char()

    # =========================
    # AMOUNTS
    # =========================
    subtotal_amount = fields.Float()
    discount_amount = fields.Float()
    vat_percent = fields.Float()
    vat_amount = fields.Float()
    total_amount = fields.Float()

    # =========================
    # OCR OUTPUT
    # =========================
    extracted_text = fields.Text(readonly=True)
    confidence_score = fields.Float(readonly=True)
    extraction_log = fields.Text(readonly=True)

    # =========================
    # LINE ITEMS (UI READY)
    # =========================
    line_ids = fields.One2many(
        "ocr.document.line",
        "document_id",
        string="Items",
    )

    # =========================
    # AUTO NAME
    # =========================
    @api.model
    def create(self, vals):
        if not vals.get("name"):
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("ocr.document")
                or "OCR-0000"
            )
        return super().create(vals)

    # =========================
    # OCR ACTION (STABLE)
    # =========================
    def action_run_ocr(self):
        for doc in self:
            if not doc.file:
                raise UserError(_("Please upload a file first."))

            doc.write({
                "status": "processing",
                "progress": 20,
            })

            try:
                import numpy as np
                import cv2

                # Decode image
                img_bytes = base64.b64decode(doc.file)
                img = cv2.imdecode(
                    np.frombuffer(img_bytes, np.uint8),
                    cv2.IMREAD_COLOR,
                )

                if img is None:
                    raise UserError(_("Invalid image file."))

                # 🔒 SAFE OCR CALL
                ocr = get_paddle_ocr()
                result = ocr.ocr(img, cls=False)

                texts = []
                confidences = []

                for block in result:
                    for line in block:
                        texts.append(line[1][0])
                        confidences.append(line[1][1])

                raw_text = "\n".join(texts)
                avg_conf = (
                    sum(confidences) / len(confidences)
                    if confidences else 0.0
                )

                # 🔥 STRUCTURED PARSING (YOUR FRIEND'S LOGIC)
                parsed = OCRParser.extract_fields(raw_text)

                # 🔥 WRITE DATA
                doc.write({
                    "status": "completed",
                    "progress": 100,

                    "vendor_name": parsed.get("vendor_name"),
                    "supplier_name": parsed.get("supplier_name"),
                    "customer_name": parsed.get("customer_name"),
                    "seller_id": parsed.get("seller_id"),
                    "company_issued": parsed.get("company_issued"),
                    "tax_id": parsed.get("tax_id"),
                    "vendor_phone": parsed.get("vendor_phone"),
                    "vendor_address": parsed.get("vendor_address"),
                    "reference_number": parsed.get("reference_number"),

                    "subtotal_amount": parsed.get("subtotal_amount"),
                    "discount_amount": parsed.get("discount_amount"),
                    "vat_percent": parsed.get("vat_percent"),
                    "vat_amount": parsed.get("vat_amount"),
                    "total_amount": parsed.get("total_amount"),

                    "confidence_score": round(avg_conf, 4),
                    "extracted_text": raw_text,
                    "extraction_log": "OCR + parsing completed successfully.",
                })

            except Exception as e:
                doc.write({
                    "status": "error",
                    "progress": 100,
                    "extraction_log": f"OCR error: {str(e)}",
                })

        return True

    # =========================
    # UI ACTIONS
    # =========================
    def action_rerun_ocr(self):
        return self.action_run_ocr()

    def action_view_image(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ocr.document",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

