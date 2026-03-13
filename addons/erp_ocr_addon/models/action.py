from odoo import models
from .ocr_helpers.vendor_bill import create_vendor_bill


class OcrDocumentActions(models.Model):
    _inherit = "ocr.document"

    def action_create_vendor_bill(self):
        return create_vendor_bill(self)

    def action_open_vendor_bill(self):
        self.ensure_one()

        if not self.vendor_bill_id:
            return

        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Bill",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.vendor_bill_id.id,
            "target": "current",
        }