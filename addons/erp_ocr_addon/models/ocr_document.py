from odoo import models, fields, api
from datetime import datetime


class OCRDocument(models.Model):
    _name = "ocr.document"
    _description = "OCR Document Storage"
    _order = "create_date desc"

    # ------------------------------
    # BASIC META INFO
    # ------------------------------

    name = fields.Char(
        string="Document Name",
        required=True,
        default=lambda self: "OCR Document"
    )

    document_type = fields.Selection(
        [
            ('invoice', 'Invoice'),
            ('receipt', 'Receipt'),
        ],
        string="Document Type",
        required=True,
        default="invoice"
    )

    file = fields.Binary(
        string="Upload File",
        attachment=True,
        required=True
    )

    filename = fields.Char(string="Filename")

    extracted_text = fields.Text(
        string="Raw OCR Text",
        help="Full text extracted from OCR before parsing"
    )

    # ------------------------------
    # PARSED / EXTRACTED FIELDS
    # ------------------------------

    vendor_name = fields.Char(string="Vendor Name")

    invoice_date = fields.Date(string="Date")

    total_amount = fields.Float(string="Total Amount")

    vat_amount = fields.Float(string="VAT Amount")

    confidence_score = fields.Float(
        string="OCR Confidence Score",
        help="Confidence from OCR / Regex extraction"
    )

    # ------------------------------
    # PROCESSING INFORMATION
    # ------------------------------

    status = fields.Selection(
        [
            ('uploaded', "Uploaded"),
            ('extracting', "Extracting..."),
            ('extracted', "Extracted"),
            ('review', "In Review"),
            ('failed', "Failed"),
            ('posted', "Posted to System")
        ],
        string="Status",
        default="uploaded"
    )

    processed_datetime = fields.Datetime(
        string="Processed Date & Time"
    )

    extraction_log = fields.Text(
        string="Extraction Log",
        help="Logs of OCR and parsing, for debugging"
    )

    linked_record_id = fields.Reference(
        [
            ('account.move', 'Vendor Bill'),
            ('hr.expense', 'Expense Record')
        ],
        string="Linked Record",
        help="Vendor bill or Expense created from this OCR"
    )

    # ------------------------------
    # AUTOMATIC LOGIC
    # ------------------------------

    @api.model
    def create(self, vals):
        # Automatically store filename if missing
        if vals.get("file") and not vals.get("filename"):
            vals["filename"] = vals.get("name")

        return super(OCRDocument, self).create(vals)

    def mark_extracted(self):
        """Called after OCR extraction."""
        for rec in self:
            rec.status = "extracted"
            rec.processed_datetime = datetime.now()

    def mark_failed(self, log_msg=None):
        """Called when extraction fails."""
        for rec in self:
            rec.status = "failed"
            rec.extraction_log = log_msg
            rec.processed_datetime = datetime.now()
