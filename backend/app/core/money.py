"""Money helpers. Every amount is a Decimal with two places; binary floats are never used."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")  # fits NUMERIC(14, 2)

CURRENCIES = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
    "SGD": "S$",
    "AUD": "A$",
    "CAD": "C$",
}


def to_money(value) -> Decimal:
    """Convert a str/int/Decimal to a two-place Decimal. Floats are rejected on purpose."""
    if isinstance(value, float):
        raise TypeError("Use a string or Decimal for money, not float.")
    try:
        d = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Not a valid amount.") from exc
    if not d.is_finite():
        raise ValueError("Not a valid amount.")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def zero() -> Decimal:
    return Decimal("0.00")


def percent(part: Decimal, whole: Decimal) -> Decimal | None:
    """part / whole × 100 to one decimal place, or None when whole is zero (no division by zero)."""
    if whole is None or whole == 0:
        return None
    return (part / whole * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_money(amount: Decimal, currency: str = "INR") -> str:
    """Format for display in AI answers and alerts, e.g. ₹1,23,456.50 for INR, $123,456.50 otherwise."""
    amount = to_money(amount)
    sign = "-" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):.2f}".partition(".")
    if currency == "INR":
        # Indian grouping: last three digits, then pairs.
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail]) if groups else tail
    else:
        whole = f"{int(whole):,}"
    symbol = CURRENCIES.get(currency, currency + " ")
    text = f"{whole}.{frac}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"{sign}{symbol}{text}"
