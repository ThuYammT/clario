from odoo.exceptions import UserError
from odoo import _
from .cleaners import normalize_phone


def create_vendor_bill(document):

    document.ensure_one()
    doc_type = document.document_type
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

    invoice_lines = []

    # ======================================================
    # 🔥 NORMAL LINES (NO TAX)
    # ======================================================
    if doc_type == "receipt":

        for line in document.line_ids:
            qty = line.quantity or 1
            unit_price = line.unit_price or 0
            line_total = line.total_amount or line.subtotal_amount or 0

            if not unit_price and line_total and qty:
                unit_price = line_total / qty

            invoice_lines.append((0, 0, {
                "name": line.description or "",
                "quantity": qty,
                "price_unit": unit_price,
                "tax_ids": False,
            }))
    else:

        for line in document.line_ids:

            qty = line.quantity or 1
            unit_price = line.unit_price or 0

            line_total = line.total_amount or line.subtotal_amount or 0

            if line_total == 0:
                qty = 1
                unit_price = 0

            elif line_total and qty > 0:
                expected_total = round(unit_price * qty, 2)

                if abs(expected_total - line_total) > 5:
                    unit_price = line_total / qty

            invoice_lines.append((0, 0, {
                "name": line.description or "",
                "quantity": qty,
                "price_unit": unit_price,
                "tax_ids": False,
            }))

    # ======================================================
    # 🔥 DISCOUNT
    # ======================================================
    if document.discount_amount and doc_type != "receipt":
        invoice_lines.append((0, 0, {
            "name": "Discount",
            "quantity": 1,
            "price_unit": document.discount_amount,
            "tax_ids": False,
        }))

    # ======================================================
    # 🔥 VAT AS SEPARATE LINE (KEY FIX)
    # ======================================================
    if document.vat_amount and document.vat_amount > 0 and doc_type != "receipt":

        if document.vat_type == "included":
            # 🔥 VAT already inside total → DO NOT add again
            invoice_lines.append((0, 0, {
                "name": f"VAT 7% (included: {document.vat_amount})",
                "quantity": 1,
                "price_unit": 0,   # ✅ DOES NOT AFFECT TOTAL
                "tax_ids": False,
            }))

        else:
            # 🔥 VAT not included → add normally
            invoice_lines.append((0, 0, {
                "name": "VAT 7%",
                "quantity": 1,
                "price_unit": document.vat_amount,
                "tax_ids": False,
            }))

    # ======================================================
    # CREATE BILL
    # ======================================================
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