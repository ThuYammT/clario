def safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def detect_currency(env, code_from_azure):

    if code_from_azure:
        cur = env["res.currency"].search(
            [("name", "=", code_from_azure)],
            limit=1
        )

        if cur:
            return cur

    return env.company.currency_id