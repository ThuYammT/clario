from odoo.exceptions import UserError
from odoo import _
from .cleaners import normalize_phone
import logging

_logger = logging.getLogger(__name__)


def create_vendor_bill(document):

    document.ensure_one()
    doc_type = document.document_type
    if document.vendor_bill_id:
        raise UserError(_("Vendor Bill already created."))

    vat = (document.vendor_tax_id or "").strip() or False
    phone = normalize_phone(document.vendor_phone)
    extracted_name = document.vendor_name or ""

    partner = False

    if vat:
        # First try: Find partner with matching tax ID AND similar name
        # Search for partners with this tax ID
        partners_with_vat = document.env["res.partner"].search([("vat", "=", vat)])

        if partners_with_vat:
            _logger.info(f"Found {len(partners_with_vat)} partners with tax ID {vat}")

            # Try to find a partner with matching name (exact or partial)
            for p in partners_with_vat:
                # Check if names match (case-insensitive, ignore extra spaces)
                p_name = p.name or ""
                if (extracted_name and extracted_name.strip() == p_name.strip()) or \
                   (extracted_name and extracted_name.strip() in p_name.strip()) or \
                   (p_name and p_name.strip() in extracted_name.strip()):
                    partner = p
                    _logger.info(f"Found matching partner by name: {p.name}")
                    break

            # If no name match found, use the first one but warn
            if not partner:
                partner = partners_with_vat[0]
                _logger.warning(f"No name match found. Using first partner: {partner.name}")

                # Optionally update the partner name if it's clearly wrong
                # (like the Japanese characters case)
                if partner.name != extracted_name and len(partners_with_vat) == 1:
                    # Only auto-update if there's just one partner with this tax ID
                    partner.write({"name": extracted_name})
                    _logger.info(f"Updated partner name from '{partner.name}' to '{extracted_name}'")

    # If no partner found, create a new one
    if not partner:
        partner = document.env["res.partner"].create({
            "name": extracted_name,
            "vat": vat,
            "phone": phone,
            "website": document.vendor_website,
            "supplier_rank": 1,
        })
        _logger.info(f"Created new partner: {extracted_name}")

    # Create invoice lines (rest of your existing code remains the same)
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