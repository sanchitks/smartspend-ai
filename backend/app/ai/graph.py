"""LangGraph workflows (PRD §7.2-7.3).

Chat:   parse_input → classify_intent → (route)
          data intents  → retrieve_financial_data → calculate_metrics → generate_insight → safety_check
          education     → generate_education → safety_check
          add expense   → extract_transaction → validate_draft
          vague period / missing % → clarify
          out of scope  → boundary
        → format_response

Parse:  parse_input → extract_transaction → validate_draft → format_response

The graph is bounded (no loops), the model never touches the database, and every number shown comes from
deterministic code. If the model is unavailable, each step falls back to rules so the assistant keeps working.
"""
import logging
import re
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.ai import grounding
from app.ai.handlers import Handlers, describe, resolve_period
from app.ai.prompts import PROMPT_VERSION
from app.ai.providers import AIOutputError, AIProvider, AIUnavailable
from app.ai.providers.mock import MockProvider
from app.core.money import MAX_AMOUNT, to_money
from app.services.categories import find_by_name

log = logging.getLogger("smartspend.ai")
_rules = MockProvider()

DATA_INTENTS = {"expense_total", "income_total", "category_summary", "budget_status", "period_comparison",
                "savings_scenario", "goal_status"}
BOUNDARY = ("I can't help with investments, tax, loans, credit or insurance decisions; a qualified professional "
            "is the right person for those. I can help with your own spending, budgets and savings goals, for "
            "example \"How much did I spend on food this month?\" or \"How much is left in my budget?\"")
OFF_TOPIC = ("I can only help with your SmartSpend records and general budgeting. Try asking \"Which category did "
             "I spend most on?\" or \"Compare this month with last month.\"")
DISCLAIMER = "This is general information, not professional financial advice."


class State(TypedDict, total=False):
    # inputs
    message: str
    ctx: dict
    previous: dict | None
    deps: dict  # {"db", "user", "provider"}: kept out of every prompt
    mode: str  # "chat" | "parse"
    # working values
    intent: str
    category: str | None
    period_kind: str
    period: Any
    percent: float | None
    data: Any
    reference: str
    facts: dict
    links: list
    candidate: str | None
    answer: str
    kind: str
    draft: dict | None
    degraded: bool
    ai_text_rejected: str | None
    route: str
    response: dict


def _provider(state: State) -> AIProvider:
    return state["deps"]["provider"]


def _degrade(state: State, step: str, exc: Exception) -> dict:
    reason = getattr(exc, "reason", None) or str(exc) or type(exc).__name__
    log.warning("ai step fell back to rules", extra={"node": step, "error_type": reason})
    return {"degraded": True}


# ---------------------------------------------------------------- nodes


def parse_input(state: State) -> dict:
    text = re.sub(r"\s+", " ", state["message"]).strip()[:1000]
    return {"message": text, "degraded": False, "ai_text_rejected": None, "draft": None, "links": []}


def classify_intent(state: State) -> dict:
    ctx = {**state["ctx"], "previous": state.get("previous")}
    update: dict = {}
    try:
        result = _provider(state).classify_intent(state["message"], ctx)
    except (AIUnavailable, AIOutputError) as exc:
        update |= _degrade(state, "classify_intent", exc)
        result = _rules.classify_intent(state["message"], ctx)
    category = result.category if result.category in ctx["categories"] else None
    today = date.fromisoformat(ctx["today"])
    period = resolve_period(result.period, today, result.n_days, result.year, result.month)
    intent = result.intent
    if intent in DATA_INTENTS:
        if period is None:
            route = "clarify"
        elif intent == "savings_scenario" and not result.percent:
            route = "clarify"
        else:
            route = "retrieve"
    elif intent == "general_budgeting":
        route = "education"
    elif intent == "add_transaction":
        route = "extract"
    else:
        route = "boundary"
    return update | {"intent": intent, "category": category, "period_kind": result.period, "period": period,
                     "percent": result.percent, "route": route}


def retrieve_financial_data(state: State) -> dict:
    """Authorised retrieval: the handler is bound to the signed-in user, never to an id from the request."""
    deps = state["deps"]
    today = date.fromisoformat(state["ctx"]["today"])
    return {"data": Handlers(deps["db"], deps["user"], today)}


def calculate_metrics(state: State) -> dict:
    h: Handlers = state["data"]
    intent, p, cat = state["intent"], state["period"], state.get("category")
    if intent == "expense_total":
        r = h.total("expense", p, cat)
    elif intent == "income_total":
        r = h.total("income", p, cat)
    elif intent == "category_summary":
        r = h.category_summary(p)
    elif intent == "budget_status":
        r = h.budget_status(p, cat)
    elif intent == "period_comparison":
        r = h.comparison(state["period_kind"], p, cat)
    elif intent == "savings_scenario":
        r = h.scenario(state["percent"], cat)
    else:
        r = h.goals()
    return {"facts": r.facts, "reference": r.reference, "links": r.links, "kind": r.kind, "data": None}


def generate_insight(state: State) -> dict:
    provider = _provider(state)
    if not provider.is_live:
        return {"candidate": None}
    try:
        text = provider.write_answer(state["message"], state["intent"], state["facts"], state["reference"],
                                     state["ctx"])
    except (AIUnavailable, AIOutputError) as exc:
        return _degrade(state, "generate_insight", exc) | {"candidate": None}
    return {"candidate": text}


def generate_education(state: State) -> dict:
    try:
        text = _provider(state).write_education(state["message"], state["ctx"])
    except (AIUnavailable, AIOutputError) as exc:
        text = _rules.write_education(state["message"], state["ctx"])
        return _degrade(state, "generate_education", exc) | {"candidate": text, "reference": text,
                                                              "facts": {"period": None, "items": [], "notes": []},
                                                              "kind": "education"}
    fallback = _rules.write_education(state["message"], state["ctx"])
    return {"candidate": text, "reference": fallback, "facts": {"period": None, "items": [], "notes": []},
            "kind": "education"}


def safety_check(state: State) -> dict:
    candidate = state.get("candidate")
    if state.get("kind") == "education":
        # No user data is involved, so only the advice boundary applies (rules of thumb like 50/30/20 are fine).
        ok = bool(candidate) and not grounding._UNSAFE.search(candidate)
        answer = candidate if ok else state["reference"]
        if DISCLAIMER.split(",")[0].lower() not in answer.lower():
            answer = answer.rstrip() + " " + DISCLAIMER
        return {"answer": answer, "ai_text_rejected": None if ok else "unsafe_advice"}
    if candidate is None:
        return {"answer": state["reference"]}
    ok, reason = grounding.check(candidate, state["facts"], state["reference"], state["message"])
    if not ok:
        log.warning("ai answer rejected by grounding check", extra={"intent": state["intent"], "error_type": reason})
        return {"answer": state["reference"], "ai_text_rejected": reason}
    return {"answer": candidate}


def clarify(state: State) -> dict:
    if state["intent"] == "savings_scenario":
        question = "By what percentage would you like to imagine cutting it? For example: \"What if I cut shopping by 15%?\""
    else:
        question = "Which period do you mean: this month, last month, or the last 30 days?"
    return {"answer": question, "kind": "clarification", "facts": {"period": None, "items": [], "notes": []}}


def boundary(state: State) -> dict:
    t = state["message"].lower()
    regulated = re.search(r"\b(invest|stock|share|crypto|bitcoin|mutual fund|sip|tax|itr|loan|emi|credit|"
                          r"insurance|trading)\b", t)
    return {"answer": BOUNDARY if regulated else OFF_TOPIC, "kind": "boundary",
            "facts": {"period": None, "items": [], "notes": []}}


def extract_transaction(state: State) -> dict:
    try:
        extracted = _provider(state).extract_transaction(state["message"], state["ctx"])
        update: dict = {}
    except (AIUnavailable, AIOutputError) as exc:
        if state.get("mode") == "parse":
            raise  # the parse endpoint reports "AI unavailable" and offers manual entry
        update = _degrade(state, "extract_transaction", exc)
        extracted = _rules.extract_transaction(state["message"], state["ctx"])
    return update | {"data": extracted}


def validate_draft(state: State) -> dict:
    """Deterministic validation of the model's proposal. Nothing is saved here."""
    deps, ctx, x = state["deps"], state["ctx"], state["data"]
    missing = set(x.missing_fields)
    amount = None
    if x.amount:
        try:
            amount = to_money(x.amount.replace("₹", "").strip())
            if amount <= 0 or amount > MAX_AMOUNT:
                amount = None
        except (ValueError, TypeError):
            amount = None
    if amount is None:
        missing.add("amount")
    kind = x.transaction_type
    if kind == "unknown":
        missing.add("transaction_type")
    category = find_by_name(deps["db"], deps["user"], x.category, kind if kind != "unknown" else None)
    if category is None:
        missing.add("category")
    elif kind == "unknown":
        kind = category.type
        missing.discard("transaction_type")
    tx_date = None
    try:
        tx_date = date.fromisoformat(x.transaction_date) if x.transaction_date else None
    except ValueError:
        pass
    if tx_date is None:
        missing.add("transaction_date")
    needs = x.needs_clarification or amount is None or kind == "unknown"
    question = x.clarification_question
    if needs and not question:
        question = "How much was it?" if amount is None else "Was this money you spent or money you received?"
    confidence = max(0.0, min(1.0, x.confidence - (0.15 if missing - set(x.missing_fields) else 0)))
    draft = {
        "draft": {
            "amount": amount, "currency": ctx["currency"], "transaction_type": kind,
            "category": category.name if category else None, "category_id": category.id if category else None,
            "description": (x.description or (category.name if category else "")).strip()[:200],
            "transaction_date": tx_date, "payment_method": x.payment_method,
        },
        "confidence": round(confidence, 2),
        "requires_confirmation": True,
        "missing_fields": sorted(missing),
        "needs_clarification": needs,
        "clarification_question": question if needs else None,
        "provider": _provider(state).name if not state.get("degraded") else "rules",
    }
    if needs:
        answer = question
        kind_out = "clarification"
    else:
        answer = "Here's what I understood. Check the details, then confirm to save it."
        kind_out = "draft"
    return {"draft": draft, "answer": answer, "kind": kind_out, "data": None,
            "facts": {"period": None, "items": [], "notes": []}}


def format_response(state: State) -> dict:
    p = state.get("period")
    provider = _provider(state)
    response = {
        "answer": state["answer"],
        "intent": state.get("intent", "add_transaction"),
        "period": ({"start": p.start, "end": p.end, "label": describe(p)}
                   if p is not None and state.get("kind") == "answer" else None),
        "facts": state.get("facts") or {"period": None, "items": [], "notes": []},
        "kind": state.get("kind", "answer"),
        "draft": state.get("draft"),
        "links": state.get("links") or [],
        "provider": "rules" if state.get("degraded") else provider.name,
        "grounded": True,  # numbers are either the calculated facts or AI text that passed the check
        "meta": {"prompt_version": PROMPT_VERSION, "model": provider.model, "degraded": bool(state.get("degraded")),
                 "ai_text_rejected": state.get("ai_text_rejected"), "category": state.get("category"),
                 "period_label": describe(p) if p is not None else None},
    }
    return {"response": response}


# ---------------------------------------------------------------- graphs


def _route(state: State) -> str:
    return state["route"]


def build_chat_graph():
    g = StateGraph(State)
    for name, fn in [("parse_input", parse_input), ("classify_intent", classify_intent),
                     ("retrieve_financial_data", retrieve_financial_data), ("calculate_metrics", calculate_metrics),
                     ("generate_insight", generate_insight), ("generate_education", generate_education),
                     ("safety_check", safety_check), ("clarify", clarify), ("boundary", boundary),
                     ("extract_transaction", extract_transaction), ("validate_draft", validate_draft),
                     ("format_response", format_response)]:
        g.add_node(name, fn)
    g.add_edge(START, "parse_input")
    g.add_edge("parse_input", "classify_intent")
    g.add_conditional_edges("classify_intent", _route, {
        "retrieve": "retrieve_financial_data", "education": "generate_education", "extract": "extract_transaction",
        "clarify": "clarify", "boundary": "boundary",
    })
    g.add_edge("retrieve_financial_data", "calculate_metrics")
    g.add_edge("calculate_metrics", "generate_insight")
    g.add_edge("generate_insight", "safety_check")
    g.add_edge("generate_education", "safety_check")
    g.add_edge("extract_transaction", "validate_draft")
    for name in ("safety_check", "clarify", "boundary", "validate_draft"):
        g.add_edge(name, "format_response")
    g.add_edge("format_response", END)
    return g.compile()


def build_parse_graph():
    g = StateGraph(State)
    g.add_node("parse_input", parse_input)
    g.add_node("extract_transaction", extract_transaction)
    g.add_node("validate_draft", validate_draft)
    g.add_edge(START, "parse_input")
    g.add_edge("parse_input", "extract_transaction")
    g.add_edge("extract_transaction", "validate_draft")
    g.add_edge("validate_draft", END)
    return g.compile()


chat_graph = build_chat_graph()
parse_graph = build_parse_graph()


def run_chat(message: str, ctx: dict, deps: dict, previous: dict | None = None) -> dict:
    state = chat_graph.invoke({"message": message, "ctx": ctx, "deps": deps, "previous": previous, "mode": "chat"},
                              {"recursion_limit": 20})
    return state["response"]


def run_parse(text: str, ctx: dict, deps: dict) -> dict:
    state = parse_graph.invoke({"message": text, "ctx": ctx, "deps": deps, "mode": "parse"}, {"recursion_limit": 10})
    return state["draft"]
