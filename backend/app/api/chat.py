"""POST /api/chat — one orchestrated turn, persisted (plan.md §2, §4).

The server holds no per-request state: the conversation history the model sees
is rebuilt from `messages` on every call, so a restart mid-chat loses nothing.

Persistence is all-or-nothing per turn. The user row, the assistant row and (on
a first message) the conversation row commit together after the turn succeeds;
a turn that dies on a provider error persists nothing, so the user can hit
"retry" without leaving a trail of unanswered duplicates in the transcript.

Rate limiting is *reported*, never hidden. A wait the budgeted provider absorbed
comes back as `queued_seconds` in the response; a 429 that outlives its retries
becomes a 503 with a Retry-After header rather than a 500, which is what lets
the UI show "queued" instead of "error".

POST /api/chat/confirm is the second half of an action turn (plan.md §7). It
takes the signed token off the confirm card, re-runs the tool through the
registry with `confirmed=True` — so RBAC is re-checked at execution time and a
role change between preview and click still denies — and never talks to the
model: the tool's own one-line result is the reply.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.budget import get_budgeted_provider, queued_notifier
from app.ai.orchestrator import TurnResult, run_turn
from app.ai.tools import confirm
from app.ai.tools.registry import REGISTRY, ToolDenied
from app.ai.providers import (
    LLMProvider,
    Msg,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
)
from app.auth.context import AuthContext
from app.auth.deps import get_auth_context, get_db
from app.models import Conversation, Message

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_MESSAGE_CHARS = 2000  # a question, not a document — bounds the prompt too
TITLE_CHARS = 60
RETRY_AFTER_SECONDS = 30  # what we tell a client when the free-tier ceiling is hit


def get_provider() -> LLMProvider:
    """A dependency so tests can swap in a scripted provider with no live key."""
    return get_budgeted_provider()


# --- wire shapes ------------------------------------------------------------

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: int | None = None


class UsageOut(BaseModel):
    tokens_in: int
    tokens_out: int


class ChatOut(BaseModel):
    conversation_id: int
    message_id: int
    text: str
    citations: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    path: str
    intent: str
    usage: UsageOut
    queued_seconds: float


class ConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    conversation_id: int | None = None  # where to file the outcome, if anywhere


class ConfirmOut(BaseModel):
    tool: str
    text: str
    result: dict[str, Any]
    conversation_id: int | None
    message_id: int | None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str | None
    citations: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    tokens_in: int | None
    tokens_out: int | None
    created_at: str


class ConversationOut(BaseModel):
    id: int
    title: str | None
    created_at: str


# --- endpoints --------------------------------------------------------------

@router.post("", response_model=ChatOut)
def chat(
    body: ChatIn,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
) -> ChatOut:
    question = body.message.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "message is empty")

    convo = _own_conversation(db, ctx, body.conversation_id) if body.conversation_id else None
    history = _history(db, convo.id) if convo else []

    waits: list[float] = []
    try:
        with queued_notifier(lambda seconds, _reason: waits.append(seconds)):
            result = run_turn(
                question=question, ctx=ctx, db=db, history=history, provider=provider
            )
    except ProviderRateLimited as exc:
        db.rollback()
        retry_after = int(exc.retry_after or RETRY_AFTER_SECONDS)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "the assistant is busy — please retry shortly",
            headers={"Retry-After": str(retry_after)},
        ) from exc
    except ProviderNotConfigured as exc:
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM provider not configured") from exc
    except ProviderError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM provider error") from exc

    if convo is None:
        convo = Conversation(user_id=ctx.user_id, title=question[:TITLE_CHARS])
        db.add(convo)
        db.flush()  # need the id for the message rows

    db.add(Message(conversation_id=convo.id, role="user", content=question))
    reply = Message(
        conversation_id=convo.id,
        role="assistant",
        content=result.text or None,
        tool_calls=_runs_json(result) or None,
        citations=result.citations or None,
        tokens_in=result.usage.tokens_in,
        tokens_out=result.usage.tokens_out,
    )
    db.add(reply)
    db.commit()

    queued = round(sum(waits), 2)
    if queued:
        response.headers["X-Queued-Seconds"] = str(queued)

    return ChatOut(
        conversation_id=convo.id,
        message_id=reply.id,
        text=result.text,
        citations=result.citations,
        cards=result.cards,
        path=result.path,
        intent=result.intent,
        usage=UsageOut(tokens_in=result.usage.tokens_in, tokens_out=result.usage.tokens_out),
        queued_seconds=queued,
    )


@router.post("/confirm", response_model=ConfirmOut)
def confirm_action(
    body: ConfirmIn,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConfirmOut:
    try:
        tool_name, args = confirm.verify(body.token, user_id=ctx.user_id)
    except confirm.TokenExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, "confirmation window closed — ask again") from exc
    except confirm.TokenUsed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "this action was already confirmed") from exc
    except confirm.ConfirmError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid confirmation token") from exc

    convo = _own_conversation(db, ctx, body.conversation_id) if body.conversation_id else None

    try:
        result = REGISTRY.invoke(tool_name, ctx, db, args, confirmed=True)
    except ToolDenied as exc:  # role changed since the preview; audited as 'denied'
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not permitted for your role") from exc
    except (KeyError, ValueError) as exc:  # token names something that is not an action tool
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid confirmation token") from exc

    if not isinstance(result, dict) or not result.get("done"):
        db.rollback()
        reason = result.get("error", "could not complete") if isinstance(result, dict) else "could not complete"
        raise HTTPException(status.HTTP_409_CONFLICT, reason)

    text = str(result.get("message") or "Done.")
    reply = None
    if convo is not None:
        reply = Message(
            conversation_id=convo.id,
            role="assistant",
            content=text,
            tool_calls=[{"name": tool_name, "args": args, "ok": True, "error": None, "preview": None, "executed": True}],
        )
        db.add(reply)
    db.commit()
    confirm.consume(body.token)  # only once the write is durable

    return ConfirmOut(
        tool=tool_name,
        text=text,
        result=result,
        conversation_id=convo.id if convo else None,
        message_id=reply.id if reply else None,
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> list[ConversationOut]:
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == ctx.user_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    ).all()
    return [
        ConversationOut(id=c.id, title=c.title, created_at=c.created_at.isoformat()) for c in rows
    ]


@router.get("/{conversation_id}", response_model=list[MessageOut])
def get_conversation(
    conversation_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    convo = _own_conversation(db, ctx, conversation_id)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=list(m.citations or []),
            cards=_cards_from_runs(m.tool_calls),
            tokens_in=m.tokens_in,
            tokens_out=m.tokens_out,
            created_at=m.created_at.isoformat(),
        )
        for m in _messages(db, convo.id)
    ]


# --- helpers ----------------------------------------------------------------

def _own_conversation(db: Session, ctx: AuthContext, conversation_id: int) -> Conversation:
    """404, not 403, for someone else's conversation: its existence is not theirs to learn."""
    convo = db.get(Conversation, conversation_id)
    if convo is None or convo.user_id != ctx.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    return convo


def _messages(db: Session, conversation_id: int) -> list[Message]:
    return db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    ).all()


def _history(db: Session, conversation_id: int) -> list[Msg]:
    """What the model sees of the past: user/assistant text only.

    Tool results and confirmation cards are not replayed — the orchestrator
    trims to the last few pairs anyway, and a stale tool table in the prompt
    would only invite the model to answer from it instead of calling the tool.
    """
    return [
        {"role": m.role, "content": m.content}
        for m in _messages(db, conversation_id)
        if m.role in ("user", "assistant") and m.content
    ]


def _runs_json(result: TurnResult) -> list[dict[str, Any]]:
    """The executed tool calls, as stored in messages.tool_calls."""
    return [
        {
            "name": r.name,
            "args": r.args,
            "ok": r.ok,
            "error": r.error,
            "preview": r.preview,
        }
        for r in result.tool_runs
    ]


def _cards_from_runs(runs: Any) -> list[dict[str, Any]]:
    """Rebuild the confirm card a stored turn stopped on, for the transcript view."""
    if not isinstance(runs, list):
        return []
    return [
        {"type": "confirm", "tool": r["name"], "args": r.get("args", {}), **r["preview"]}
        for r in runs
        if isinstance(r, dict) and r.get("ok") and isinstance(r.get("preview"), dict)
    ]
