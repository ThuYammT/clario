import re


def normalize_phone(phone):
    if not phone:
        return phone

    phone = str(phone).strip()

    for ch in [" ", "-", "(", ")", ".", "\t", "\n", "\r"]:
        phone = phone.replace(ch, "")

    return phone


def format_structured_address(addr_struct):
    if not addr_struct or not isinstance(addr_struct, dict):
        return None

    raw = addr_struct.get("raw")
    if raw:
        raw = raw.replace("\n", " ")
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    parts = []
    seen = set()

    for key in [
        "house",
        "unit",
        "street_address",
        "house_number",
        "road",
        "city_district",
        "city",
        "postal_code",
        "country_region",
    ]:
        val = addr_struct.get(key)

        if val:
            clean_val = val.replace("\n", " ")
            clean_val = re.sub(r"\s+", " ", clean_val).strip()

            if clean_val not in seen:
                seen.add(clean_val)
                parts.append(clean_val)

    return ", ".join(parts) if parts else None


def clean_vendor_name(name):
    if not name:
        return name

    name = name.replace("\n", " ").strip()

    name = re.sub(
        r"\|\s*.*?(รหัสสาขา|Branch).*?$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(r"\s+", " ", name).strip()

    return name


def clean_text_field(value):
    if not value:
        return value

    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()

    return value