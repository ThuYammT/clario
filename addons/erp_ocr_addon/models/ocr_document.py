# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .ocr_parser import OCRParser


class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document"
    _order = "create_date desc"

    # -------------------------
    # BASIC FIELDS
    # -------------------------
    name = fields.Char(string="Document Name", required=True)
    file = fields.Binary(string="File", attachment=True, required=True)
    doc_type = fields.Selection(
        [
            ("invoice", "Invoice"),
            ("receipt", "Receipt"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
    )
    upload_date = fields.Datetime(
        string="Uploaded On",
        default=lambda self: fields.Datetime.now(),
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True,
    )

    # -------------------------
    # STATUS
    # -------------------------
    status = fields.Selection(
        [
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("error", "Error"),
        ],
        string="Status",
        default="uploaded",
    )
    progress = fields.Integer(string="Progress (%)", default=0)

    # -------------------------
    # OCR RESULT FIELDS
    # -------------------------
    vendor_name = fields.Char(string="Vendor / Shop Name")
    invoice_date = fields.Date(string="Invoice / Receipt Date")

    total_amount = fields.Float(string="Total Amount")
    vat_amount = fields.Float(string="VAT Amount")
    confidence_score = fields.Float(string="OCR Confidence Score")

    extracted_text = fields.Text(string="Raw OCR Text")
    extraction_log = fields.Text(string="Extraction Log")

    # For history filtering / dashboard
    is_invoice = fields.Boolean(string="Is Invoice", compute="_compute_type_flags")
    is_receipt = fields.Boolean(string="Is Receipt", compute="_compute_type_flags")

    def _compute_type_flags(self):
        for rec in self:
            rec.is_invoice = rec.doc_type == "invoice"
            rec.is_receipt = rec.doc_type == "receipt"

    # ------------------------------------------
    # AUTO-GENERATE DOCUMENT NAME USING SEQUENCE
    # ------------------------------------------
    @api.model
    def create(self, vals):
        # If no name was given, auto-generate one
        if not vals.get("name"):
            seq = self.env["ir.sequence"].next_by_code("ocr.document") or "OCR-0000"
            vals["name"] = seq
        return super().create(vals)

    # -------------------------
    # MAIN OCR ACTION
    # -------------------------
    def action_run_ocr(self):
        """
        Called from the form 'Run OCR' button.
        - Uses OCRParser to run Tesseract on self.file
        - Fills fields and marks status/progress
        """
        for doc in self:
            if not doc.file:
                raise UserError(_("Please upload a file before running OCR."))

            # Mark as processing
            doc.write({
                "status": "processing",
                "progress": 10,
            })

            text = OCRParser.run_tesseract(doc.file)

            if text.startswith("OCR ERROR:"):
                # Mark as error and store message in log
                new_log = (doc.extraction_log or "") + "\n" + text
                doc.write({
                    "status": "error",
                    "progress": 100,
                    "extracted_text": text,
                    "extraction_log": new_log.strip(),
                })
                continue

            # Parse fields
            data = OCRParser.extract_fields(text)

            log_lines = [
                "=== OCR Extraction ===",
                f"Vendor: {data.get('vendor_name', '')}",
                f"Total: {data.get('total_amount', 0.0)}",
                f"VAT: {data.get('vat_amount', 0.0)}",
                f"Confidence: {data.get('confidence', 0.0)}",
            ]
            if data.get("invoice_date_raw"):
                log_lines.append(f"Raw date: {data['invoice_date_raw']}")

            # NOTE: we keep invoice_date empty for now (raw date in log)
            vals = {
                "status": "completed",
                "progress": 100,
                "vendor_name": data.get("vendor_name") or False,
                "total_amount": data.get("total_amount") or 0.0,
                "vat_amount": data.get("vat_amount") or 0.0,
                "confidence_score": data.get("confidence") or 0.0,
                "extracted_text": text,
                "extraction_log": ((doc.extraction_log or "") + "\n" + "\n".join(log_lines)).strip(),
            }

            doc.write(vals)

        return True

    # -------------------------
    # ACTIONS USED FROM TREE / UI
    # -------------------------
    def action_rerun_ocr(self):
        """
        Called from the 'Re-run OCR' button in the history tree.
        Just calls action_run_ocr again.
        """
        for rec in self:
            rec.action_run_ocr()
        return True

    def action_view_image(self):
        """
        Open form view (same record) so the user can see the file + result.
        Used by the 'View' button in history tree.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ocr.document",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }