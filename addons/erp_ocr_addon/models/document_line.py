# -*- coding: utf-8 -*-
from odoo import models, fields, api

class OCRDocumentLine(models.Model):
    _name = "ocr.document.line"
    _description = "OCR Document Line Item"
    _order = "sequence asc, id asc"

    # ======================================================
    # 1. RELATION & ORDERING
    # ======================================================
    document_id = fields.Many2one(
        "ocr.document",
        string="Document",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)

    # ======================================================
    # 2. ITEM IDENTIFICATION
    # ======================================================
    # Your View uses 'product_code' and 'description'
    product_code = fields.Char(string="Product Code")
    description = fields.Text(string="Description")
    
    # Friend's 'item_no' mapped to your 'product_code' for compatibility
    item_no = fields.Char(string="Item No.", related="product_code", store=False)
    
    # Robust Char field for Item Number (prevents crashes on non-numeric IDs)
    item_number = fields.Char(string="Item Number")
    item_name = fields.Char(string="Item Name")

    # ======================================================
    # 3. QUANTITY & PRICE
    # ======================================================
    quantity = fields.Float(string="Quantity", default=1.0)
    unit_price = fields.Float(string="Unit Price")
    
    # Your View looks for 'discount_amount'
    discount_amount = fields.Float(string="Discount Amount", default=0.0)
    # Friend's View looks for 'discount' -> We link them so both work
    discount = fields.Float(string="Discount", related="discount_amount", store=True, readonly=False)

    # ======================================================
    # 4. TAX SUPPORT
    # ======================================================
    # Friend uses 'vat_rate', You use 'tax_rate'. We sync them.
    vat_rate = fields.Float(string="VAT Rate (%)", default=0.0)
    tax_rate = fields.Float(string="Tax Rate", related="vat_rate", store=True, readonly=False)
    
    vat_amount = fields.Float(string="VAT Amount")

    # ======================================================
    # 5. TOTALS (Hybrid Naming)
    # ======================================================
    # Your XML needs 'subtotal_excl_tax'
    subtotal_excl_tax = fields.Float(
        string="Subtotal (Excl. Tax)",
        compute="_compute_totals",
        store=True,
    )
    # Friend's XML needs 'line_subtotal' -> Synced
    line_subtotal = fields.Float(
        string="Line Subtotal", 
        related="subtotal_excl_tax", 
        store=False
    )

    # Your XML needs 'total_incl_tax'
    total_incl_tax = fields.Float(
        string="Total (Incl. Tax)",
        compute="_compute_totals",
        store=True,
    )

    # Both use 'line_total' (usually meaning the final payable for that line)
    line_total = fields.Float(
        string="Line Total",
        compute="_compute_totals",
        store=True,
    )

    rounding_adjustment = fields.Float(string="Rounding Adjustment", default=0.0)
    amount_in_words = fields.Char(string="Amount in Words")

    # ======================================================
    # 6. COMPUTE LOGIC (The Robust Version)
    # ======================================================
    @api.depends(
        "quantity",
        "unit_price",
        "discount_amount",
        "vat_rate",
        "rounding_adjustment",
    )
    def _compute_totals(self):
        for line in self:
            qty = line.quantity or 0.0
            price = line.unit_price or 0.0
            disc = line.discount_amount or 0.0

            # 1. Base Subtotal
            subtotal = (qty * price) - disc
            
            # Sanity check: Subtotal shouldn't be negative unless it's a credit note line
            if subtotal < 0 and price > 0: 
                subtotal = 0.0

            line.subtotal_excl_tax = subtotal

            # 2. Calculate VAT
            # Uses 'vat_rate' (which is synced to tax_rate)
            rate = line.vat_rate or 0.0
            tax_amt = 0.0
            if rate and subtotal:
                tax_amt = subtotal * (rate / 100.0)
            
            # 3. Final Total
            total = subtotal + tax_amt + (line.rounding_adjustment or 0.0)

            line.vat_amount = tax_amt
            line.total_incl_tax = total
            line.line_total = total