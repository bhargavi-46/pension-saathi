"""Pension Saathi API — FastAPI backend.

Run locally:
    uvicorn main:app --reload
Docs at /docs.
"""

import asyncio
import json
import uuid

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from agents import whatsapp_handler
from services import whatsapp_client as wa
from services.voice import voice_service

from agents import discovery_agent, document_agent, filing_agent, onboarding_agent
from agents.tracking_agent import tracking_loop
from db import AgentAction, Claim, Conversation, SessionLocal, Widow, init_db
from scripts.seed_demo import seed_if_needed
from services import crypto as doc_crypto
from services.gemini import gemini_service, is_quota_error
from services.ocr import ocr_service
from services.rag import scheme_rag
from services.web_search import web_search_service

app = FastAPI(title="Pension Saathi API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost(:\d+)?|127\.0\.0\.1(:\d+)?|.*\.vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    seed_if_needed()
    asyncio.create_task(tracking_loop())


# ------------------------------------------------------------------- basics
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mock_mode": gemini_service.mock,
        "gemini_keys": len(gemini_service.api_keys),
        "groq_fallback": gemini_service.groq.enabled,
        "embeddings_degraded_to_mock": gemini_service._embed_mock and gemini_service.has_gemini,
        "chat_model": gemini_service.chat_model_name,
        "embed_model": gemini_service.embed_model_name,
        "web_search_provider": web_search_service.provider.name,
        "server_side_ocr": ocr_service.enabled,
        "ocr_langs": ocr_service.langs,
        "docs_encrypted_at_rest": doc_crypto.enabled,
    }


class PromptIn(BaseModel):
    prompt: str


@app.post("/test-gemini")
def test_gemini(body: PromptIn) -> dict:
    return {"response": gemini_service.chat(body.prompt)}


# ------------------------------------------------------------------ schemes
class SearchIn(BaseModel):
    query: str
    profile: dict | None = None


@app.post("/search-schemes")
def search_schemes(body: SearchIn) -> dict:
    results = scheme_rag.search(body.query, top_k=8)
    if body.profile:
        results = scheme_rag.filter_by_profile(body.profile, results)
    return {"results": results}


@app.get("/schemes")
def all_schemes() -> dict:
    return {"schemes": scheme_rag.schemes}


# ─────────────────────────────────────────────── dedicated web search
# Called directly, NOT via Gemini grounding. Provider auto-selected from
# whichever WEB_SEARCH key is set (Tavily / Serper / Brave); mock otherwise.
class WebSearchIn(BaseModel):
    query: str
    top_k: int = 5


@app.post("/search-web")
def search_web(body: WebSearchIn) -> dict:
    return web_search_service.search(body.query, top_k=body.top_k)


# ─────────────────────────────────────────────── Sarvam voice for the web
# The web /chat page uses the browser's Web Speech API by default (free,
# on-device). But desktop browsers don't ship Indian-language voices, so
# Telugu / Tamil / Bengali fall silent on many machines. This endpoint lets
# the frontend fall back to server-side Sarvam TTS — the same code path
# WhatsApp uses — so voice works on any device regardless of installed voices.
from fastapi.responses import Response


class TTSIn(BaseModel):
    text: str
    lang: str = "hi"  # 'hi' | 'te' | 'en' | 'ta' | 'bn'


@app.post("/voice/tts")
def voice_tts(body: TTSIn) -> Response:
    lang = (body.lang or "hi").split("-")[0].lower()
    audio = voice_service.text_to_speech(body.text, lang=lang)
    if not audio:
        raise HTTPException(503, "Server-side TTS not configured (set SARVAM_API_KEY).")
    # Sarvam returns WAV, ElevenLabs returns MP3. audio/mpeg is a safe superset
    # for the <audio> element to play either — browsers sniff the container.
    return Response(content=audio, media_type="audio/mpeg")


# -------------------------------------------------------------------- widow
class WidowIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    state: str | None = None
    district: str | None = None
    age: int | None = None
    children_count: int | None = None
    monthly_income: int | None = None
    husband_occupation: str | None = None
    husband_death_date: str | None = None


@app.post("/widow")
def create_widow(body: WidowIn) -> dict:
    with SessionLocal() as db:
        widow = Widow(id=str(uuid.uuid4())[:8], **body.model_dump())
        db.add(widow)
        db.commit()
        return widow.to_dict()


@app.get("/widow/{widow_id}")
def get_widow(widow_id: str) -> dict:
    with SessionLocal() as db:
        widow = db.get(Widow, widow_id)
        if widow is None:
            raise HTTPException(404, "Widow not found")
        return widow.to_dict()


class MessageIn(BaseModel):
    role: str
    content: str


@app.post("/widow/{widow_id}/message")
def append_message(widow_id: str, body: MessageIn) -> dict:
    with SessionLocal() as db:
        msg = Conversation(widow_id=widow_id, role=body.role, content=body.content)
        db.add(msg)
        db.commit()
        return msg.to_dict()


@app.get("/widow/{widow_id}/messages")
def list_messages(widow_id: str) -> dict:
    with SessionLocal() as db:
        rows = (
            db.query(Conversation)
            .filter_by(widow_id=widow_id)
            .order_by(Conversation.id)
            .all()
        )
        return {"messages": [r.to_dict() for r in rows]}


@app.get("/widow/{widow_id}/claims")
def list_claims(widow_id: str) -> dict:
    with SessionLocal() as db:
        rows = db.query(Claim).filter_by(widow_id=widow_id).order_by(Claim.id).all()
        claims = [r.to_dict() for r in rows]
        return {
            "claims": claims,
            "total_annual_value": sum(c["estimated_annual_value"] for c in claims),
        }


# ------------------------------------------------------------------- agents
class OnboardingIn(BaseModel):
    widow_id: str
    message: str
    language: str | None = None  # e.g. "te-IN" from the app's language setting


@app.post("/agent/onboarding/message")
def onboarding_message(body: OnboardingIn) -> dict:
    return onboarding_agent.handle_message(body.widow_id, body.message, body.language)


@app.post("/agent/document/upload")
async def document_upload(
    widow_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    file_bytes = await file.read()
    try:
        return document_agent.process_document(widow_id, doc_type, file_bytes, file.filename or "upload.jpg")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        if is_quota_error(e):
            raise HTTPException(
                429,
                "Gemini free-tier limit reached — wait about a minute and try again.",
            )
        # Surface a readable reason in the chat instead of a bare 500
        raise HTTPException(502, f"AI error while reading the document: {str(e)[:200]}")


class WidowRef(BaseModel):
    widow_id: str


@app.post("/agent/discovery/run")
def discovery_run(body: WidowRef) -> dict:
    return discovery_agent.run_discovery(body.widow_id)


@app.post("/agent/prepare/run")
async def prepare_run(body: WidowRef, background_tasks: BackgroundTasks) -> dict:
    """Assess documents on file, submit the ready schemes, and return what to
    ask her for next. Called after discovery and after every document upload."""
    result = filing_agent.prepare_and_submit(body.widow_id)
    if result["submitted"]:
        background_tasks.add_task(filing_agent.simulate_progress, body.widow_id)
    return result


# ---------------------------------------------------------------------- SSE
@app.get("/agent/stream/{widow_id}")
async def agent_stream(widow_id: str) -> StreamingResponse:
    """Server-Sent Events: stream agent_actions rows for this widow as they
    appear (simple 1s poll on the table — plenty for a demo)."""

    async def event_source():
        with SessionLocal() as db:
            rows = (
                db.query(AgentAction)
                .filter_by(widow_id=widow_id)
                .order_by(AgentAction.id)
                .all()
            )
            last_id = rows[-1].id if rows else 0
            for row in rows:
                yield f"data: {json.dumps(row.to_dict(), ensure_ascii=False)}\n\n"

        while True:
            await asyncio.sleep(1)
            with SessionLocal() as db:
                rows = (
                    db.query(AgentAction)
                    .filter(AgentAction.widow_id == widow_id, AgentAction.id > last_id)
                    .order_by(AgentAction.id)
                    .all()
                )
            for row in rows:
                last_id = row.id
                yield f"data: {json.dumps(row.to_dict(), ensure_ascii=False)}\n\n"
            yield ": keep-alive\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ WhatsApp
@app.get("/whatsapp/webhook")
def whatsapp_verify(request: Request) -> PlainTextResponse:
    """Meta calls this once to verify the webhook. Echo the challenge back if
    the verify token matches."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == wa.VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(403, "verification failed")


@app.post("/whatsapp/webhook")
async def whatsapp_receive(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Receive incoming WhatsApp messages (text, voice notes, images) and route
    them to the conversation handler. Replies are sent asynchronously so we ack
    Meta immediately."""
    body = await request.json()
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    _dispatch_whatsapp_message(msg, background_tasks)
    except Exception as e:
        print(f"[whatsapp] webhook parse error: {str(e)[:150]}")
    return {"status": "received"}


def _dispatch_whatsapp_message(msg: dict, background_tasks: BackgroundTasks) -> None:
    phone = msg.get("from")
    mtype = msg.get("type")
    if not phone:
        return
    if mtype == "text":
        background_tasks.add_task(whatsapp_handler.handle_text, phone, msg["text"]["body"])
    elif mtype == "audio":
        media_id = msg["audio"]["id"]
        background_tasks.add_task(_wa_media_task, "voice", phone, media_id)
    elif mtype == "image":
        media_id = msg["image"]["id"]
        background_tasks.add_task(_wa_media_task, "image", phone, media_id)


def _wa_media_task(kind: str, phone: str, media_id: str) -> None:
    data = wa.download_media(media_id)
    if not data:
        return
    if kind == "voice":
        whatsapp_handler.handle_voice(phone, data)
    else:
        whatsapp_handler.handle_image(phone, data)
