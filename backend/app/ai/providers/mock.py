"""Offline demo provider: rule-based parsing and intent detection, no network and no API key.

Used in tests, in local demos without a key, and whenever AI_PROVIDER=mock. It follows the same output contracts
as the Claude adapter, so the rest of the app can't tell them apart.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from app.ai.providers.base import AIProvider, ExtractedTransaction, InsightText, IntentResult

EXPENSE_WORDS = {
    "Food & Dining": ["dinner", "lunch", "breakfast", "restaurant", "cafe", "café", "coffee", "swiggy", "zomato", "food",
                      "pizza", "snack", "tea", "chai", "meal", "burger", "biryani", "dining", "dine", "eat out"],
    "Groceries": ["grocery", "groceries", "vegetable", "milk", "supermarket", "bigbasket", "blinkit", "zepto", "fruit",
                  "kirana", "dmart"],
    "Transportation": ["uber", "ola", "cab", "taxi", "auto", "metro", "bus", "fuel", "petrol", "diesel", "parking",
                       "toll", "rapido", "transport", "commute"],
    "Shopping": ["amazon", "flipkart", "myntra", "clothes", "shoes", "shopping", "shirt", "jeans", "electronics",
                 "gadget", "headphones"],
    "Entertainment": ["movie", "cinema", "concert", "game", "pvr", "show", "party", "bowling", "entertainment"],
    "Healthcare": ["doctor", "medicine", "pharmacy", "hospital", "medical", "clinic", "dentist", "chemist", "health"],
    "Education": ["course", "book", "tuition", "school", "college", "udemy", "exam", "education", "fees"],
    "Housing & Rent": ["rent", "landlord", "maintenance", "housing"],
    "Utilities": ["electricity", "water bill", "gas bill", "internet", "wifi", "wi-fi", "broadband", "phone bill",
                  "recharge", "utility", "utilities", "bill"],
    "Travel": ["flight", "hotel", "trip", "vacation", "airbnb", "irctc", "holiday", "travel"],
    "Subscriptions": ["netflix", "spotify", "prime", "subscription", "hotstar", "youtube premium", "icloud",
                      "membership"],
    "Personal Care": ["salon", "haircut", "spa", "gym", "cosmetic", "grooming", "personal care"],
}
INCOME_WORDS = {
    "Salary": ["salary", "payroll", "paycheck", "stipend"],
    "Freelance": ["freelance", "client", "invoice", "project payment", "gig"],
    "Business": ["business", "sales", "shop income"],
    "Gift": ["gift", "birthday money"],
    "Refund": ["refund", "cashback", "reimbursement", "returned"],
}
EXPENSE_VERBS = r"\b(spent|spend|paid|pay|bought|buy|purchased?|ordered|booked|recharged?|cost|gave)\b"
INCOME_VERBS = r"\b(received|receive|got paid|earned|earn|credited|salary|income|bonus|sold|refund(?:ed)?|cashback)\b"
PAYMENTS = [("upi", r"\b(upi|gpay|google pay|phonepe|paytm upi|bhim)\b"), ("cash", r"\bcash\b"),
            ("credit_card", r"\bcredit card\b"), ("debit_card", r"\bdebit card\b"),
            ("net_banking", r"\b(net ?banking|neft|imps)\b"), ("wallet", r"\b(wallet|paytm)\b")]
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr|\$|usd|€|£)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(k|lakh|lakhs|l)?\b"
    r"\s*(?:rupees|rs|inr)?", re.IGNORECASE)


def _words_match(text: str, words: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(w), text) for w in words)


def _find_category(text: str, table: dict) -> str | None:
    for name, words in table.items():
        if _words_match(text, words):
            return name
    return None


def _amount(text: str) -> str | None:
    # Skip numbers that are clearly dates ("on 15th", "2026-11-12", "12 Nov").
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    cleaned = re.sub(r"\b\d{1,2}(st|nd|rd|th)\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}\s+(" + "|".join(MONTHS) + r")\b", " ", cleaned, flags=re.IGNORECASE)
    for m in _AMOUNT.finditer(cleaned):
        raw, unit = m.group(1).replace(",", ""), (m.group(2) or "").lower()
        value = Decimal(raw)
        if unit == "k":
            value *= 1_000
        elif unit in ("lakh", "lakhs", "l"):
            value *= 100_000
        if value > 0:
            return f"{value:.2f}"
    return None


def _date(text: str, today: date) -> date:
    t = text.lower()
    if "day before yesterday" in t:
        return today - timedelta(days=2)
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\b", t)
    if m:
        try:
            d = date(today.year, MONTHS[m.group(2)], int(m.group(1)))
            return d if d <= today else d.replace(year=today.year - 1)
        except ValueError:
            pass
    m = re.search(r"\b(?:last|on)\s+(" + "|".join(WEEKDAYS) + r")\b", t)
    if m:
        back = (today.weekday() - WEEKDAYS.index(m.group(1))) % 7 or 7
        return today - timedelta(days=back)
    return today


_EDGE_WORDS = {"on", "for", "at", "the", "a", "an", "my", "in", "of", "to", "from", "i", "we", "and", "via", "using",
               "with", "by", "through"}


def _describe(text: str, category: str | None) -> str:
    """'Spent ₹450 on dinner at a restaurant today' → 'Dinner at a restaurant'."""
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    t = re.sub(r"\b(?:on\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(_AMOUNT, " ", t)
    t = re.sub(EXPENSE_VERBS + "|" + INCOME_VERBS, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(day before yesterday|yesterday|today|tonight|this morning|this evening)\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:last|on)\s+(" + "|".join(WEEKDAYS) + r")\b", " ", t, flags=re.IGNORECASE)
    for _, pattern in PAYMENTS:
        t = re.sub(r"\b(?:via|using|with|by|through)?\s*" + pattern.removeprefix(r"\b"), " ", t, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[\s,.!?]+", t) if w and not w.isdigit()]
    while words and words[0].lower() in _EDGE_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _EDGE_WORDS:
        words.pop()
    desc = " ".join(words[:8]).strip()
    return (desc[:1].upper() + desc[1:]) if desc else (category or "")


class MockProvider(AIProvider):
    name = "demo"

    def extract_transaction(self, text: str, ctx: dict) -> ExtractedTransaction:
        t = text.lower()
        today = date.fromisoformat(ctx["today"])
        amount = _amount(text)
        if re.search(INCOME_VERBS, t):
            kind = "income"
        elif re.search(EXPENSE_VERBS, t):
            kind = "expense"
        else:
            kind = "unknown"
        exp_cat = _find_category(t, EXPENSE_WORDS)
        inc_cat = _find_category(t, INCOME_WORDS)
        if kind == "unknown" and exp_cat:
            kind = "expense"
        elif kind == "unknown" and inc_cat:
            kind = "income"
        category = exp_cat if kind == "expense" else inc_cat if kind == "income" else None
        if kind == "income" and category is None and exp_cat == "Shopping" and "refund" in t:
            category = "Refund"
        payment = next((name for name, pattern in PAYMENTS if re.search(pattern, t)), None)
        description = _describe(text, category)

        missing = [f for f, v in (("amount", amount), ("transaction_type", kind != "unknown" or None),
                                  ("category", category)) if not v]
        question = None
        if amount is None:
            question = "How much was it?"
        elif kind == "unknown":
            question = "Was this money you spent or money you received?"
        elif category is None and len(description.split()) < 2:
            question = "What was it for?"
        confidence = round(1.0 - 0.25 * len(missing), 2)
        return ExtractedTransaction(
            amount=amount, currency=ctx["currency"], transaction_type=kind, category=category,
            description=description or "", transaction_date=_date(text, today).isoformat(), payment_method=payment,
            confidence=max(confidence, 0.1), missing_fields=missing, needs_clarification=question is not None,
            clarification_question=question,
        )

    def classify_intent(self, message: str, ctx: dict) -> IntentResult:
        t = message.lower().strip()
        today = date.fromisoformat(ctx["today"])
        period, n_days, year, month = _period(t, today)
        category = _category_in_question(t, ctx["categories"])
        pct = re.search(r"(\d{1,2}(?:\.\d)?)\s*(%|percent)", t)
        percent = float(pct.group(1)) if pct else None
        is_question = bool(re.search(r"\?|\b(how|what|which|where|when|did|do|does|am|is|are|can|should|show|tell)\b", t))

        def result(intent, conf=0.8):
            return IntentResult(intent=intent, category=category, period=period, n_days=n_days, year=year,
                                month=month, percent=percent, confidence=conf)

        if re.search(r"\b(invest|stock|shares?|crypto|bitcoin|mutual funds?|\bsip\b|tax|itr|loan|emi|credit score|"
                     r"insurance|trading|nifty|sensex|gold rate)\b", t):
            return result("out_of_scope", 0.9)
        previous = ctx.get("previous")
        if previous and re.match(r"^(and|what about|how about|same for)\b", t) and previous.get("intent"):
            r = result(previous["intent"], 0.7)
            if r.category is None and previous.get("category"):
                r.category = previous["category"]
            return r
        if not is_question and _amount(message) and (re.search(EXPENSE_VERBS, t) or re.search(INCOME_VERBS, t)):
            return result("add_transaction", 0.85)
        if (re.search(r"\b(how (do|can|should) i|how to|tips?|ideas?|advice|ways? to|what is|what's)\b", t)
                and not re.search(r"\b(how much|how many|my (food|budget|spending)|this month|last month)\b", t)):
            return result("general_budgeting", 0.7)
        if re.search(r"\bwhat if\b|\b(cut|reduce|lower|trim)\b.*\d", t):
            return result("savings_scenario")
        if re.search(r"\b(compare|compared|vs\.?|versus|more than last|less than last|than last)\b", t):
            return result("period_comparison")
        if re.search(r"\b(goal|goals|saving for|savings target)\b", t):
            return result("goal_status")
        if re.search(r"\b(budget|left|remaining|over budget|within budget)\b", t) and is_question:
            return result("budget_status")
        if re.search(r"\b(which category|what category|most on|biggest|top categor|largest|where .*money go|"
                     r"spend the most|spent the most)\b", t):
            return result("category_summary")
        if re.search(r"\b(earn|earned|income|received|salary)\b", t) and is_question:
            return result("income_total")
        if re.search(r"\b(spend|spent|spending|expense|expenses|cost me)\b", t):
            return result("expense_total")
        if re.search(r"\b(budget|save|saving|savings|emergency fund|50/30/20|track|tips?|habit|overspend|"
                     r"afford|money)\b", t):
            return result("general_budgeting", 0.6)
        return result("out_of_scope", 0.5)

    def write_answer(self, question, intent, facts, reference, ctx):
        return None  # the calculated reference answer is used as is

    def write_education(self, question: str, ctx: dict) -> str:
        t = question.lower()
        if "emergency" in t:
            body = ("An emergency fund is money set aside for surprises like a medical bill or a gap in income. "
                    "A common aim is a few months of essential expenses, built up gradually. "
                    "Keep it separate from everyday spending so it isn't used by accident.")
        elif "subscription" in t:
            body = ("List every subscription and when it renews. Cancel ones you haven't used in the last month, "
                    "and set a reminder before annual renewals.")
        elif "50/30/20" in t or "rule" in t:
            body = ("The 50/30/20 idea splits take-home pay into needs (50%), wants (30%) and savings (20%). "
                    "It's a starting point: adjust the split to fit your income and fixed costs.")
        else:
            body = ("Start from what you actually spend: track a month of expenses, then set limits a little "
                    "below your current totals for the categories you can control. Pay yourself first by moving "
                    "savings out at the start of the month, and review your budget weekly rather than only at "
                    "month-end.")
        return body + " This is general information, not professional financial advice."

    def explain_insights(self, insights: list[dict], ctx: dict) -> list[InsightText] | None:
        return None


# ---------------------------------------------------------------- helpers shared with tests

def _period(t: str, today: date) -> tuple[str, int | None, int | None, int | None]:
    if re.search(r"\b(recently|lately|these days|nowadays|a while)\b", t):
        return "ambiguous", None, None, None
    m = re.search(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", t)
    if m:
        return "last_n_days", int(m.group(1)), None, None
    if "this month" in t or "so far" in t:  # checked first: "compare this month with last month" is about now
        return "this_month", None, None, None
    if "last month" in t or "previous month" in t:
        return "last_month", None, None, None
    if "last week" in t:
        return "last_week", None, None, None
    if "this week" in t:
        return "this_week", None, None, None
    if "yesterday" in t:
        return "yesterday", None, None, None
    if "today" in t:
        return "today", None, None, None
    if "this year" in t:
        return "this_year", None, None, None
    m = re.search(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(\d{4}))?", t)
    if m and not (m.group(1) == "may" and not m.group(2) and re.search(r"\bmay i\b", t)):
        month = MONTHS[m.group(1)]
        year = int(m.group(2)) if m.group(2) else (today.year if month <= today.month else today.year - 1)
        return "specific_month", None, year, month
    return "unspecified", None, None, None


SYNONYMS = {
    "food": "Food & Dining", "dining": "Food & Dining", "eating out": "Food & Dining", "restaurant": "Food & Dining",
    "transport": "Transportation", "travelling to work": "Transportation", "commute": "Transportation",
    "cab": "Transportation", "fuel": "Transportation", "rent": "Housing & Rent", "housing": "Housing & Rent",
    "bills": "Utilities", "grocery": "Groceries", "shopping": "Shopping", "movies": "Entertainment",
    "health": "Healthcare", "medical": "Healthcare", "subscriptions": "Subscriptions", "travel": "Travel",
    "salary": "Salary", "freelance": "Freelance",
}


def _category_in_question(t: str, names: list[str]) -> str | None:
    for name in sorted(names, key=len, reverse=True):
        if name.lower() in t:
            return name
    for word, name in SYNONYMS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", t) and name in names:
            return name
    return None
