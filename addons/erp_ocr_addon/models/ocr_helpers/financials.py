def compute_financials(data, safe_float):
    
    discount_val = safe_float(data.get("discount_amount")) or 0.0
    vat_val = safe_float(data.get("vat_amount")) or 0.0

    azure_subtotal = safe_float(data.get("subtotal_amount"))
    azure_total = safe_float(data.get("total_amount"))

    items_sum = 0.0
    items_list = data.get("items") or []

    found_any = False
    vat_included = False


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
      # Detect VAT included case
    # ==========================================
    # 🔥 VAT TYPE DETECTION (FIXED)
    # ==========================================
    vat_type = "unknown"

    if items_sum is not None and azure_total is not None:

        # Case 1: VAT INCLUDED
        if abs(items_sum - azure_total) < 5:
            vat_type = "included"

        # Case 2: VAT EXCLUDED
        elif vat_val and abs(items_sum + vat_val - azure_total) < 5:
            vat_type = "excluded"

    # Fallback (safe)
    if vat_type == "unknown":
        vat_type = "excluded"

    vat_included = (vat_type == "included")
    subtotal_excl_vat_excl_discount = 0
    subtotal_incl_vat_excl_discount = 0
    subtotal_excl_vat_incl_discount = 0
    total_payable = 0

    if items_sum is not None:

        if vat_included:
            gross_excl_vat = round(items_sum / 1.07, 2)
            gross_incl_vat = round(items_sum, 2)  # ✅ already includes VAT
        else:
            gross_excl_vat = items_sum
            gross_incl_vat = round(gross_excl_vat + vat_val, 2)

        # Normalize discount (always negative)
        if discount_val > 0:
            discount_val = -discount_val

        net_excl_vat = round(gross_excl_vat + discount_val, 2)
        net_incl_vat = round(net_excl_vat + vat_val, 2)

        subtotal_excl_vat_excl_discount = gross_excl_vat
        subtotal_incl_vat_excl_discount = gross_incl_vat

        # If Azure already gives final total, trust it
        if azure_total is not None:
            total_payable = round(azure_total, 2)

            # If VAT exists, derive net excl VAT from final total
            if vat_val:
                subtotal_excl_vat_incl_discount = round(total_payable - vat_val, 2)
            else:
                subtotal_excl_vat_incl_discount = round(total_payable, 2)
        else:
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
        "vat_type": vat_type,
        "debug_text": debug_text,
    }