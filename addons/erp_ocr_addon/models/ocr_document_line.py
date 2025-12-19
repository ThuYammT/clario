# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OCRDocumentLine(models.Model):
    _name = "ocr.document.line"
    _description = "OCR Document Line"

    document_id = fields.Many2one(
        "ocr.document",
        string="Document",
        required=True,
        ondelete="cascade",
    )

    item_number = fields.Char()
    item_name = fields.Char()
    description = fields.Text()

    quantity = fields.Float(default=1.0)
    unit_price = fields.Float()

    line_total = fields.Float(
        compute="_compute_line_total",
        store=True,
    )

    @api.depends("quantity", "unit_price")
    def _compute_line_total(self):
        for rec in self:
            rec.line_total = rec.quantity * rec.unit_price
