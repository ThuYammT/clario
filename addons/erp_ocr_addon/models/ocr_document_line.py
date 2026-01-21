# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OCRDocumentLine(models.Model):
    _name = "ocr.document.line"
    _description = "OCR Document Line"
    _order = "id"

    document_id = fields.Many2one(
        "ocr.document",
        ondelete="cascade",
        required=True,
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
        for line in self:
            line.line_total = (line.quantity or 0.0) * (line.unit_price or 0.0)
