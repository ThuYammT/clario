from odoo import models, fields

class OCRPreviewWizard(models.TransientModel):
    _name = "ocr.preview.wizard"
    _description = "OCR Preview Wizard Placeholder"

    name = fields.Char()

    def action_confirm(self):
        """Placeholder logic so the view doesn't crash."""
        return True
