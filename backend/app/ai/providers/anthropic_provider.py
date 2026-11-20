"""Claude adapter (Anthropic Messages API with structured outputs)."""
import json
import logging
import time

import anthropic
from pydantic import BaseModel, ValidationError

from app.ai import prompts
from app.ai.providers.base import (
    INTENTS,
    PAYMENT_METHODS,
    PERIODS,
    AIOutputError,
    AIProvider,
    AIUnavailable,
    ExtractedTransaction,
    InsightText,
    InsightTexts,
    IntentResult,
    TextAnswer,
)

log = logging.getLogger("smartspend.ai")

# On a safety decline the API re-runs the request on a fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def _object(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _user_text(text: str) -> str:
    # Keep the user's words clearly fenced off as data.
    return "<user_text>\n" + text.replace("</user_text>", "") + "\n</user_text>"


class AnthropicProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    @property
    def is_live(self) -> bool:
        return True

    def _call(self, task: str, system: str, user: str, schema: dict, out: type[BaseModel],
              effort: str = "low", max_tokens: int = 4000):
        started = time.perf_counter()
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise AIUnavailable("rate_limited") from exc
        except anthropic.APITimeoutError as exc:
            raise AIUnavailable("timeout") from exc
        except anthropic.APIConnectionError as exc:
            raise AIUnavailable("connection") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            log.error("claude credentials rejected", extra={"provider": self.name, "error_type": type(exc).__name__})
            raise AIUnavailable("credentials") from exc
        except anthropic.BadRequestError as exc:
            log.error("claude rejected the request", extra={"provider": self.name, "error_type": type(exc).__name__})
            raise AIOutputError("bad_request") from exc
        except anthropic.APIStatusError as exc:
            raise AIUnavailable(f"status_{exc.status_code}") from exc
        finally:
            log.info("claude call", extra={"provider": self.name, "model": self.model, "node": task,
                                            "duration_ms": round((time.perf_counter() - started) * 1000)})
        if resp.stop_reason == "refusal":
            raise AIOutputError("refusal")
        if resp.stop_reason == "max_tokens":
            raise AIOutputError("truncated")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise AIOutputError("empty")
        try:
            return out.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AIOutputError("invalid_output") from exc

    # ---------------------------------------------------------------- tasks

    def extract_transaction(self, text: str, ctx: dict) -> ExtractedTransaction:
        schema = _object({
            "amount": _nullable({"type": "string"}),
            "currency": _nullable({"type": "string"}),
            "transaction_type": {"type": "string", "enum": ["income", "expense", "unknown"]},
            "category": _nullable({"type": "string"}),
            "description": {"type": "string"},
            "transaction_date": _nullable({"type": "string"}),
            "payment_method": _nullable({"type": "string", "enum": list(PAYMENT_METHODS)}),
            "confidence": {"type": "number"},
            "missing_fields": {"type": "array", "items": {"type": "string"}},
            "needs_clarification": {"type": "boolean"},
            "clarification_question": _nullable({"type": "string"}),
        })
        user = (
            f"Current date: {ctx['today']} ({ctx['weekday']}), timezone {ctx['timezone']}, locale {ctx['locale']}.\n"
            f"Account currency: {ctx['currency']}.\n"
            f"Allowed expense categories: {', '.join(ctx['expense_categories'])}.\n"
            f"Allowed income categories: {', '.join(ctx['income_categories'])}.\n"
            f"Allowed payment methods: {', '.join(PAYMENT_METHODS)}.\n\n" + _user_text(text)
        )
        return self._call("extract_transaction", prompts.EXTRACT_SYSTEM, user, schema, ExtractedTransaction)

    def classify_intent(self, message: str, ctx: dict) -> IntentResult:
        schema = _object({
            "intent": {"type": "string", "enum": list(INTENTS)},
            "category": _nullable({"type": "string"}),
            "period": {"type": "string", "enum": list(PERIODS)},
            "n_days": _nullable({"type": "integer"}),
            "year": _nullable({"type": "integer"}),
            "month": _nullable({"type": "integer"}),
            "percent": _nullable({"type": "number"}),
            "confidence": {"type": "number"},
        })
        previous = ctx.get("previous")
        user = (
            f"Current date: {ctx['today']} ({ctx['weekday']}).\n"
            f"Allowed category names: {', '.join(ctx['categories'])}.\n"
            + (f"Previous turn: intent={previous.get('intent')}, category={previous.get('category')}, "
               f"period={previous.get('period_label')}.\n" if previous else "")
            + "\n" + _user_text(message)
        )
        return self._call("classify_intent", prompts.INTENT_SYSTEM, user, schema, IntentResult)

    def write_answer(self, question: str, intent: str, facts: dict, reference: str, ctx: dict) -> str | None:
        user = (
            f"Calculated facts (JSON):\n{json.dumps(facts, ensure_ascii=False, sort_keys=True)}\n\n"
            f"A correct but plain answer: {reference}\n\nQuestion:\n" + _user_text(question)
        )
        result = self._call("write_answer", prompts.ANSWER_SYSTEM, user, _object({"answer": {"type": "string"}}),
                            TextAnswer)
        return result.answer.strip()

    def write_education(self, question: str, ctx: dict) -> str:
        result = self._call("write_education", prompts.EDUCATION_SYSTEM, _user_text(question),
                            _object({"answer": {"type": "string"}}), TextAnswer, effort="medium")
        return result.answer.strip()

    def explain_insights(self, insights: list[dict], ctx: dict) -> list[InsightText] | None:
        if not insights:
            return []
        schema = _object({"items": {"type": "array", "items": _object({
            "id": {"type": "string"}, "summary": {"type": "string"}, "suggested_action": {"type": "string"},
        })}})
        payload = [{k: i[k] for k in ("id", "title", "summary", "suggested_action", "evidence", "limitations")}
                   for i in insights]
        user = "Observations (JSON):\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        result = self._call("explain_insights", prompts.INSIGHTS_SYSTEM, user, schema, InsightTexts)
        return result.items
