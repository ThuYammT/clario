def compute_financials(data, safe_float):

    discount_val = safe_float(data.get("discount_amount")) or 0.0
    vat_val = safe_float(data.get("vat_amount")) or 0.0

    azure_subtotal = safe_float(data.get("subtotal_amount"))
    azure_total = safe_float(data.get("total_amount"))

    items_sum = 0.0
    items_list = data.get("items") or []

    found_any = False

    for item in items_list:

        amt = safe_float(item.get("amount"))
        qty = safe_float(item.get("quantity"))
        unit = safe_float(item.get("unit_price"))

        if amt is not None:
            items_sum += amt
            found_any = True

        elif qty is not None and unit is not None:
            items_sum += qty * unit
            found_any = True

    items_sum = round(items_sum, 2) if found_any else None

    subtotal_excl_vat_excl_discount = 0
    subtotal_incl_vat_excl_discount = 0
    subtotal_excl_vat_incl_discount = 0
    total_payable = 0

    if items_sum is not None:

        gross_excl_vat = items_sum
        gross_incl_vat = round(gross_excl_vat + vat_val, 2)

        net_excl_vat = round(gross_excl_vat - discount_val, 2)
        net_incl_vat = round(net_excl_vat + vat_val, 2)

        subtotal_excl_vat_excl_discount = gross_excl_vat
        subtotal_incl_vat_excl_discount = gross_incl_vat
        subtotal_excl_vat_incl_discount = max(net_excl_vat, 0)
        total_payable = net_incl_vat

    debug_text = f"""
    subtotal_excl_vat_excl_discount: {subtotal_excl_vat_excl_discount}
    subtotal_incl_vat_excl_discount: {subtotal_incl_vat_excl_discount}
    subtotal_excl_vat_incl_discount: {subtotal_excl_vat_incl_discount}
    total_payable: {total_payable}
    """

    return {
        "subtotal_excl_vat_excl_discount": subtotal_excl_vat_excl_discount,
        "subtotal_incl_vat_excl_discount": subtotal_incl_vat_excl_discount,
        "subtotal_excl_vat_incl_discount": subtotal_excl_vat_incl_discount,
        "total_payable": total_payable,
        "discount_val": discount_val,
        "vat_val": vat_val,
        "debug_text": debug_text,
    }