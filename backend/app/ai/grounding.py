"""Grounding and safety checks applied to every piece of model-written text before a user sees it.

Rule: every number in an AI answer must equal a number the application calculated (or one the user typed).
If any number doesn't match, the AI text is rejected and the deterministic template answer is used instead.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

# Numbers like 1,23,456.50 / 12,000 / 92.5 / 7 (currency symbols and % are stripped around them).
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w])")

# Phrases that would turn budgeting help into regulated advice or promises.
_UNSAFE = re.compile(
    r"\b(guarantee[sd]?|risk[- ]free|you should invest|invest in|buy (?:shares|stocks|crypto)|stock tip|"
    r"tax[- ]saving scheme|financial advisor approved|will definitely save)\b",
    re.IGNORECASE,
)


def _numbers_in_text(text: str) -> list[Decimal]:
    out = []
    for m in _NUMBER.finditer(text):
        try:
            out.append(Decimal(m.group(1).replace(",", "")))
        except InvalidOperation:
            continue
    return out


def allowed_numbers(*sources) -> set[Decimal]:
    """Every number found anywhere in the given facts/strings, normalised (so 450 == 450.00)."""
    found: set[Decimal] = set()

    def walk(v):
        if v is None or isinstance(v, bool):
            return
        if isinstance(v, (int, Decimal)):
            found.add(Decimal(v).normalize())
            # Rounded forms a writer might reasonably use: whole units and one decimal place.
            if isinstance(v, Decimal):
                found.add(v.quantize(Decimal("1")).normalize())
                found.add(v.quantize(Decimal("0.1")).normalize())
        elif isinstance(v, float):
            found.add(Decimal(str(v)).normalize())
        elif isinstance(v, date):
            found.update({Decimal(v.day), Decimal(v.month), Decimal(v.year)})
        elif isinstance(v, str):
            for n in _numbers_in_text(v):
                found.add(n.normalize())
                found.add(n.quantize(Decimal("1")).normalize())
                found.add(n.quantize(Decimal("0.1")).normalize())
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)
        elif isinstance(v, (list, tuple, set)):
            for item in v:
                walk(item)

    for s in sources:
        walk(s)
    return found


def ungrounded_numbers(text: str, allowed: set[Decimal]) -> list[str]:
    return [str(n) for n in _numbers_in_text(text) if n.normalize() not in allowed]


def check(text: str | None, *sources) -> tuple[bool, str]:
    """(ok, reason). ok is False when the text has an unsupported number or unsafe advice."""
    if not text or not text.strip():
        return False, "empty"
    if _UNSAFE.search(text):
        return False, "unsafe_advice"
    bad = ungrounded_numbers(text, allowed_numbers(*sources))
    if bad:
        return False, "ungrounded_numbers"
    return True, "ok"
