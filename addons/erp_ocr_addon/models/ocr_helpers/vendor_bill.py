from odoo.exceptions import UserError
from odoo import _
from .cleaners import normalize_phone


def create_vendor_bill(document):

    document.ensure_one()

    if document.vendor_bill_id:
        raise UserError(_("Vendor Bill already created."))

    vat = (document.vendor_tax_id or "").strip() or False
    phone = normalize_phone(document.vendor_phone)

    partner = document.env["res.partner"].search(
        [("vat", "=", vat)],
        limit=1
    )

    if not partner:
        partner = document.env["res.partner"].create({
            "name": document.vendor_name,
            "vat": vat,
            "phone": phone,
            "website": document.vendor_website,
            "supplier_rank": 1,
        })

    tax_7 = document.env["account.tax"].search([
        ("amount", "=", 7),
        ("type_tax_use", "=", "purchase"),
    ], limit=1)

    invoice_lines = []

    for line in document.line_ids:

        unit_price = line.unit_price or 0

        if document.vat_amount:
            unit_price = round(unit_price / 1.07, 6)

        invoice_lines.append((0, 0, {
            "name": line.description or "",
            "quantity": line.quantity or 1,
            "price_unit": unit_price,
            "tax_ids": [(6, 0, [tax_7.id])] if tax_7 else False,
        }))

    bill = document.env["account.move"].create({
        "move_type": "in_invoice",
        "partner_id": partner.id,
        "invoice_date": document.invoice_date,
        "invoice_origin": document.name,
        "invoice_line_ids": invoice_lines,
    })

    document.vendor_bill_id = bill.id

    return {
        "type": "ir.actions.act_window",
        "res_model": "account.move",
        "res_id": bill.id,
        "view_mode": "form",
    }