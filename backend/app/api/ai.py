"""AI endpoints: transaction parsing, the SpendWise AI assistant, and insights (PRD §6.6, §6.8, §7)."""
import logging

from fastapi import APIRouter, Depends, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.context import build_ctx
from app.ai.graph import run_chat, run_parse
from app.ai.providers import AIOutputError, AIUnavailable, get_provider
from app.api.deps import current_user
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.periods import today_in
from app.core.security import RateLimiter, enforce
from app.database import get_db, utcnow
from app.models import ChatConversation, ChatMessage, User
from app.schemas import ChatIn, ChatMessageOut, ChatOut, ConversationOut, InsightsOut, ParseIn, ParseOut
from app.services import insights as insight_service

router = APIRouter(tags=["ai"])
log = logging.getLogger("smartspend.ai")
AI_LIMIT = RateLimiter(get_settings().ai_requests_per_10_min, 10 * 60)
DISCLAIMER = "SmartSpend AI provides general budgeting assistance, not regulated financial advice."
MAX_MESSAGES_PER_CONVERSATION = 200


def _limit(user: User) -> None:
    enforce(AI_LIMIT, f"user:{user.id}", "You've sent a lot of AI requests. Please wait a few minutes.")


@router.get("/ai/status")
def status(user: User = Depends(current_user)):
    p = get_provider()
    return {"provider": p.name, "live": p.is_live, "model": p.model, "disclaimer": DISCLAIMER}


@router.post("/ai/transactions/parse", response_model=ParseOut)
def parse(body: ParseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Returns a draft only. Nothing is saved until the client POSTs the confirmed draft to /transactions."""
    _limit(user)
    ctx = build_ctx(db, user, body.locale, body.timezone)
    try:
        return run_parse(body.text, ctx, {"db": db, "user": user, "provider": get_provider()})
    except (AIUnavailable, AIOutputError) as exc:
        log.warning("parse unavailable", extra={"error_type": getattr(exc, "reason", type(exc).__name__)})
        raise AppError(503, "AI_UNAVAILABLE",
                       "AI help is temporarily unavailable. You can still add the transaction manually.") from exc


@router.post("/ai/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _limit(user)
    if body.conversation_id:
        convo = db.scalar(select(ChatConversation).where(ChatConversation.id == body.conversation_id,
                                                         ChatConversation.user_id == user.id))
        if convo is None:
            raise not_found("Conversation")
    else:
        title = body.message if len(body.message) <= 60 else body.message[:57].rstrip() + "…"
        convo = ChatConversation(user_id=user.id, title=title)
        db.add(convo)
        db.flush()

    last = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id == convo.id, ChatMessage.role == "assistant")
                     .order_by(ChatMessage.id.desc()).limit(1))
    previous = None
    if last and last.meta.get("intent"):
        previous = {"intent": last.meta.get("intent"), "category": last.meta.get("category"),
                    "period_label": last.meta.get("period_label")}

    ctx = build_ctx(db, user)
    result = run_chat(body.message, ctx, {"db": db, "user": user, "provider": get_provider()}, previous)
    meta = result.pop("meta")

    db.add(ChatMessage(conversation_id=convo.id, role="user", content=body.message))
    stored = jsonable_encoder({k: v for k, v in result.items() if k != "answer"}) | {
        "category": meta["category"], "period_label": meta["period_label"], "prompt_version": meta["prompt_version"],
        "model": meta["model"], "degraded": meta["degraded"], "ai_text_rejected": meta["ai_text_rejected"],
    }
    reply = ChatMessage(conversation_id=convo.id, role="assistant", content=result["answer"], meta=stored)
    db.add(reply)
    convo.updated_at = utcnow()
    db.commit()
    _trim(db, convo.id)
    log.info("chat answered", extra={"intent": result["intent"], "provider": result["provider"]})
    return ChatOut(conversation_id=convo.id, message_id=reply.id, **result)


def _trim(db: Session, conversation_id: int) -> None:
    """Retention: keep only the most recent messages of a long conversation."""
    ids = db.scalars(select(ChatMessage.id).where(ChatMessage.conversation_id == conversation_id)
                     .order_by(ChatMessage.id.desc()).offset(MAX_MESSAGES_PER_CONVERSATION)).all()
    if ids:
        db.execute(delete(ChatMessage).where(ChatMessage.id.in_(ids)))
        db.commit()


@router.get("/ai/conversations", response_model=list[ConversationOut])
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(ChatConversation).where(ChatConversation.user_id == user.id)
                           .order_by(ChatConversation.updated_at.desc()).limit(50)))


@router.get("/ai/conversations/{conversation_id}/messages", response_model=list[ChatMessageOut])
def messages(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    convo = db.scalar(select(ChatConversation).where(ChatConversation.id == conversation_id,
                                                     ChatConversation.user_id == user.id))
    if convo is None:
        raise not_found("Conversation")
    return list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == convo.id)
                           .order_by(ChatMessage.id)))


@router.delete("/ai/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    convo = db.scalar(select(ChatConversation).where(ChatConversation.id == conversation_id,
                                                     ChatConversation.user_id == user.id))
    if convo is None:
        raise not_found("Conversation")
    db.delete(convo)
    db.commit()
    return Response(status_code=204)


@router.delete("/ai/conversations", status_code=204)
def clear_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(ChatConversation).where(ChatConversation.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.post("/ai/insights", response_model=InsightsOut)
def insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _limit(user)
    provider = get_provider()
    items = insight_service.generate(db, user, today_in(user.timezone))
    items, degraded = insight_service.reword(items, provider, build_ctx(db, user))
    return InsightsOut(insights=items, provider="rules" if degraded or not provider.is_live else provider.name,
                       disclaimer=DISCLAIMER)
