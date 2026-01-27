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
        index=True,
    )

    # Enterprise fields
    item_no = fields.Char(string="Item No.")
    description = fields.Text(string="Description")
    quantity = fields.Float(default=1.0)
    unit_price = fields.Float(string="Unit Price")

    discount = fields.Float(string="Discount", default=0.0)   # per-line discount amount
    vat_rate = fields.Float(string="VAT Rate (%)", default=0.0)

    line_subtotal = fields.Float(string="Line Subtotal", compute="_compute_totals", store=True)
    line_vat = fields.Float(string="Line VAT", compute="_compute_totals", store=True)
    line_total = fields.Float(string="Line Total", compute="_compute_totals", store=True)

    # Backward compatibility (your old fields in views/data)
    item_number = fields.Char(string="(Old) Item Number", compute="_compute_compat", store=False)
    item_name = fields.Char(string="(Old) Item Name", compute="_compute_compat", store=False)

    @api.depends("item_no", "description")
    def _compute_compat(self):
        for line in self:
            line.item_number = line.item_no or ""
            # you previously used item_name, but Azure mainly gives Description.
            # keep it populated for any old tree view that displays item_name.
            line.item_name = (line.description or "")[:80] if line.description else ""

    @api.depends("quantity", "unit_price", "discount", "vat_rate")
    def _compute_totals(self):
        for line in self:
            qty = line.quantity or 0.0
            unit = line.unit_price or 0.0
            disc = line.discount or 0.0

            subtotal = (qty * unit) - disc
            if subtotal < 0:
                subtotal = 0.0

            vat = 0.0
            if line.vat_rate and subtotal:
                vat = (subtotal * (line.vat_rate / 100.0))

            line.line_subtotal = subtotal
            line.line_vat = vat
            line.line_total = subtotal + vat
