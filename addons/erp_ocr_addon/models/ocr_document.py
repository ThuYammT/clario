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
    confidence_score = fields.Float(string="OCR Confidence Score")

    # Extra recommended fields
    invoice_number = fields.Char(string="Invoice Number")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id.id
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

    processed_datetime = fields.Datetime(string="Processed Date & Time")
    extraction_log = fields.Text(string="Extraction Log")

    linked_record_id = fields.Reference(
        [
            ('account.move', 'Vendor Bill'),
            ('hr.expense', 'Expense Record')
        ],
        string="Linked Record"
    )

    # ------------------------------
    # METHODS
    # ------------------------------

    @api.model
    def create(self, vals):
        if vals.get("file") and not vals.get("filename"):
            vals["filename"] = vals.get("name")
        return super().create(vals)

    # STATUS UPDATE HELPERS
    def mark_extracted(self):
        for rec in self:
            rec.status = "extracted"
            rec.processed_datetime = datetime.now()

    def mark_failed(self, log_msg=None):
        for rec in self:
            rec.status = "failed"
            rec.extraction_log = log_msg
            rec.processed_datetime = datetime.now()

    # Button: Run OCR
    def action_run_ocr(self):
        """Temporary placeholder OCR logic until real OCR is connected."""
        for rec in self:
            rec.status = "extracting"

            # Placeholder
            rec.extracted_text = "SAMPLE OCR TEXT"
            rec.vendor_name = "Sample Vendor"
            rec.total_amount = 123.45
            rec.vat_amount = 7.00
            rec.invoice_date = datetime.now().date()
            rec.confidence_score = 0.95

            rec.mark_extracted()
