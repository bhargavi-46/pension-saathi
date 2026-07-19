"""WhatsApp conversation handler — runs the SAME agent flow as the web app,
but orchestrated on the server so it works over WhatsApp (text or voice notes,
and photos of documents).

Flow per phone number (widow_id = "wa-<phone>"):
  1. Text/voice  -> onboarding agent (5 questions), reply by text + voice note.
  2. First photo -> death certificate -> confirm.
     After onboarding is done and the certificate is in, auto-run discovery +
     filing and send a summary of schemes (submitted / docs-needed / visit-office).
  3. More photos -> auto-classified as Aadhaar / passbook / ration card
     (in that order) -> re-run filing -> send an updated summary.
"""

from agents import discovery_agent, document_agent, filing_agent, onboarding_agent
from agents.onboarding_agent import detect_language
from db import Claim, SessionLocal, Widow, uploaded_doc_types
from services.rag import scheme_rag
from services.voice import voice_service
from services import whatsapp_client as wa

# Order in which photos are interpreted if the type isn't otherwise known.
DOC_ORDER = ["death_certificate", "aadhaar", "bank_passbook", "ration_card"]


def _widow_id(phone: str) -> str:
    return f"wa-{phone}"


def _reply(phone: str, text: str, lang: str) -> None:
    """Send a text reply, plus a voice note when server-side TTS is available."""
    wa.send_text(phone, text)
    audio = voice_service.text_to_speech(text, lang)
    if audio:
        wa.send_audio(phone, audio)


def _next_doc_type(widow_id: str) -> str:
    have = uploaded_doc_types(widow_id)
    for d in DOC_ORDER:
        if d not in have:
            return d
    return "ration_card"


def _lang_of(widow_id: str, fallback: str = "en") -> str:
    with SessionLocal() as db:
        w = db.get(Widow, widow_id)
    code = (w.language if w else "en-IN") or "en-IN"
    return code.split("-")[0]


def _scheme_summary(widow_id: str, lang: str) -> str:
    with SessionLocal() as db:
        claims = db.query(Claim).filter_by(widow_id=widow_id).order_by(
            Claim.estimated_annual_value.desc()
        ).all()
    if not claims:
        return ""
    total = sum(c.estimated_annual_value for c in claims)
    submitted = [c for c in claims if c.status in ("filed", "tracking", "received")]
    action = [c for c in claims if c.status == "action_needed"]
    lines = []
    header = {
        "hi": f"मुझे {len(claims)} योजनाएँ मिलीं — कुल ₹{total:,}/वर्ष तक की सहायता।",
        "te": f"మీకు {len(claims)} పథకాలు దొరికాయి — సంవత్సరానికి ₹{total:,} వరకు సహాయం.",
        "en": f"I found {len(claims)} schemes — up to ₹{total:,}/year of support.",
    }.get(lang, f"I found {len(claims)} schemes — up to ₹{total:,}/year of support.")
    lines.append(header)
    if submitted:
        lines.append({
            "hi": "\n✅ ऑनलाइन आवेदन कर दिया गया:",
            "te": "\n✅ ఆన్‌లైన్‌లో దరఖాస్తు చేయబడింది:",
            "en": "\n✅ Applied online:",
        }.get(lang))
        for c in submitted:
            lines.append(f"• {scheme_rag.by_id.get(c.scheme_id, {}).get('name','').split('/')[-1].strip()}"
                         + (f" ({c.tracking_id})" if c.tracking_id else ""))
    if action:
        lines.append({
            "hi": "\n🏢 इनके लिए दफ़्तर जाना होगा:",
            "te": "\n🏢 వీటికి కార్యాలయానికి వెళ్ళాలి:",
            "en": "\n🏢 These need an office visit:",
        }.get(lang))
        for c in action:
            name = scheme_rag.by_id.get(c.scheme_id, {}).get("name", "").split("/")[-1].strip()
            lines.append(f"• {name}\n   {c.notes or ''}")
    return "\n".join(l for l in lines if l)


def _run_discovery_and_filing(phone: str, widow_id: str, lang: str) -> None:
    result = discovery_agent.run_discovery(widow_id)
    if result.get("followup_question"):
        # Information gap: the pipeline halted — ask her the clarifying
        # question and wait; her answer resumes discovery via handle_text.
        _reply(phone, result["followup_question"], lang)
        return
    filing_agent.prepare_and_submit(widow_id)
    summary = _scheme_summary(widow_id, lang)
    if summary:
        _reply(phone, summary, lang)
    ask = {
        "hi": "पैसा आपके खाते में आने के लिए कृपया अपना आधार कार्ड और बैंक पासबुक की फोटो भी भेजें।",
        "te": "డబ్బు మీ ఖాతాలో పడాలంటే దయచేసి మీ ఆధార్ కార్డు, బ్యాంక్ పాస్‌బుక్ ఫోటోలు కూడా పంపండి.",
        "en": "To receive the money, please also send photos of your Aadhaar card and bank passbook.",
    }.get(lang)
    _reply(phone, ask, lang)


# --------------------------------------------------------------- entry points
def handle_text(phone: str, text: str) -> None:
    widow_id = _widow_id(phone)
    lang = detect_language(text) if text else _lang_of(widow_id)
    if lang == "en":
        lang = _lang_of(widow_id)  # keep established language on ASCII replies
    res = onboarding_agent.handle_message(widow_id, text)
    _reply(phone, res["agent_reply"], detect_language(res["agent_reply"]))
    if res.get("resume_discovery"):
        # She just answered the information-gap question — re-run discovery
        # with the completed profile and continue to filing.
        _run_discovery_and_filing(phone, widow_id, _lang_of(widow_id))


def handle_voice(phone: str, audio_bytes: bytes) -> None:
    widow_id = _widow_id(phone)
    lang = _lang_of(widow_id, "hi")
    text = voice_service.speech_to_text(audio_bytes, lang)
    if not text:
        _reply(phone, "Sorry, I could not hear that. Please type your answer.", lang)
        return
    handle_text(phone, text)


def handle_image(phone: str, image_bytes: bytes) -> None:
    widow_id = _widow_id(phone)
    lang = _lang_of(widow_id, "en")
    doc_type = _next_doc_type(widow_id)
    try:
        doc = document_agent.process_document(widow_id, doc_type, image_bytes, "wa.jpg")
    except Exception as e:
        _reply(phone, f"I couldn't read that document clearly. Please resend. ({str(e)[:60]})", lang)
        return

    d = doc.get("extracted_data") or {}
    if doc_type == "death_certificate":
        confirm = {
            "hi": f"मैंने प्रमाण पत्र पढ़ लिया है। आपके पति {d.get('deceased_name','')} का देहांत {d.get('date_of_death','')} को हुआ। अब मैं आपकी योजनाएँ खोज रही हूँ…",
            "te": f"ధృవీకరణ పత్రం చదివాను. మీ భర్త {d.get('deceased_name','')} {d.get('date_of_death','')} న మరణించారు. ఇప్పుడు మీ పథకాలు వెతుకుతున్నాను…",
            "en": f"I've read the certificate — your husband {d.get('deceased_name','')} passed away on {d.get('date_of_death','')}. Now finding your schemes…",
        }.get(lang)
        _reply(phone, confirm, lang)
        with SessionLocal() as db:
            w = db.get(Widow, widow_id)
            done = w and (w.onboarding_step or 0) >= 5
        if done:
            _run_discovery_and_filing(phone, widow_id, lang)
    else:
        got = {
            "hi": f"{doc_type.replace('_',' ')} मिल गया ✓ अब बाकी योजनाओं की जाँच कर रही हूँ…",
            "te": f"{doc_type.replace('_',' ')} అందింది ✓ ఇప్పుడు మిగతా పథకాలను చూస్తున్నాను…",
            "en": f"Got your {doc_type.replace('_',' ')} ✓ Re-checking your schemes…",
        }.get(lang)
        _reply(phone, got, lang)
        filing_agent.prepare_and_submit(widow_id)
        summary = _scheme_summary(widow_id, lang)
        if summary:
            _reply(phone, summary, lang)
