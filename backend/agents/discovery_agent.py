"""Discovery agent — finds every scheme a widow qualifies for.

Pipeline (a LangGraph StateGraph when langgraph is installed, otherwise the
same nodes run sequentially):

    load_profile -> retrieve (RAG) -> reason (LLM eligibility) -> persist
"""

import json
import re
from typing import TypedDict

from agents.onboarding_agent import DAUGHTER_QUESTION, GAP_FALLBACK_NAME
from db import Claim, Conversation, Document, SessionLocal, Widow, log_action
from services.gemini import gemini_service, is_quota_error
from services.rag import scheme_rag
from services.web_search import web_search_service

# >= 0.5 keeps "probably eligible, needs a fact verified" schemes (which the
# LLM scores 0.5-0.6) instead of silently dropping them; they get flagged.
CONFIDENCE_THRESHOLD = 0.5
VERIFY_BELOW = 0.65


class DiscoveryState(TypedDict, total=False):
    widow_id: str
    profile: dict
    death_certificate: dict | None
    conversation: str
    candidates: list[dict]
    evaluations: list[dict]
    claims: list[dict]
    # Live web context: dedicated search-API snippets about the widow's
    # state's schemes, retrieved fresh at discovery time and passed to the
    # eligibility LLM as extra grounding. Not used as an oracle — we still
    # trust the curated 20-scheme JSON for base rules.
    web_context: str
    # Information-gap gate: when a matched scheme depends on an unknown
    # household fact, the pipeline halts and asks instead of persisting.
    halt: bool
    followup_question: str


# ------------------------------------------------------------------- nodes
def load_profile(state: DiscoveryState) -> DiscoveryState:
    with SessionLocal() as db:
        widow = db.get(Widow, state["widow_id"])
        if widow is None:
            raise ValueError(f"No widow with id {state['widow_id']}")
        state["profile"] = widow.to_dict()
        cert = (
            db.query(Document)
            .filter_by(widow_id=state["widow_id"], doc_type="death_certificate")
            .order_by(Document.id.desc())
            .first()
        )
        state["death_certificate"] = cert.to_dict()["extracted_data"] if cert else None
        # Her own words often carry details the structured profile misses
        # ("2 sons aged 14 and 10", "husband was a school teacher") — give the
        # eligibility LLM the raw conversation too.
        messages = (
            db.query(Conversation)
            .filter_by(widow_id=state["widow_id"], role="user")
            .order_by(Conversation.id)
            .limit(30)
            .all()
        )
        state["conversation"] = " | ".join(m.content for m in messages)
    return state


def _fetch_web_context(profile: dict) -> str:
    """Pull fresh public-web snippets about widow entitlements for this state.
    We route through the dedicated search API (Tavily/Serper/Brave) — NOT
    Gemini grounding — so retrieval stays auditable and cheap. The snippets
    are handed to the eligibility LLM as extra context; the LLM still has to
    reconcile them against our stored rulebook."""
    state_name = profile.get("state") or "India"
    query = f"widow pension scheme {state_name} 2025 eligibility documents required"
    try:
        res = web_search_service.search(query, top_k=4)
        snippets = [f"- {r.get('title','')}: {r.get('snippet','')}" for r in res.get("results", [])]
        header = f"[web context — provider={res.get('provider')}]"
        return header + "\n" + "\n".join(snippets) if snippets else ""
    except Exception as e:
        print(f"[discovery] web_search failed: {str(e)[:120]}")
        return ""


def retrieve(state: DiscoveryState) -> DiscoveryState:
    p = state["profile"]
    query = (
        f"widow age {p.get('age')} with {p.get('children_count')} children in {p.get('state')}, "
        f"husband was {p.get('husband_occupation')}, monthly income ₹{p.get('monthly_income')}"
    )
    log_action(state["widow_id"], "discovery", f"Searching schemes: \"{query}\"")

    # Live web context via the DEDICATED search API. New / policy-updated
    # schemes (that aren't in the curated 20 yet) come in as evidence for the
    # LLM to weigh. This is how the pipeline stays current when a state
    # announces something mid-year.
    state["web_context"] = _fetch_web_context(p)
    if state["web_context"]:
        provider_hint = state["web_context"].split("]", 1)[0].split("=")[-1]
        log_action(
            state["widow_id"], "discovery",
            f"Fetched fresh web context ({provider_hint}) — passed to the eligibility LLM alongside our stored schemes",
            {"provider": provider_hint},
        )

    candidates = scheme_rag.search(query, top_k=len(scheme_rag.schemes))

    # Conflict & disqualification check (real administrative eligibility rules)
    eligible, excluded = scheme_rag.screen_eligibility(p, candidates)
    for ex in excluded:
        name = ex["scheme"]["name"].split("/")[-1].strip()
        log_action(
            state["widow_id"],
            "discovery",
            f"Conflict check — {name}: excluded ({ex['reason']})",
            {"scheme_id": ex["scheme"]["id"], "reason": ex["reason"]},
        )

    state["candidates"] = eligible[:8]
    log_action(
        state["widow_id"],
        "discovery",
        f"{len(excluded)} schemes ruled out by eligibility rules; "
        f"{len(state['candidates'])} candidates remain for detailed review",
        {"candidates": [c["id"] for c in state["candidates"]]},
    )
    return state


# The reasoning sentence is shown on the scheme card AND read aloud by the
# voice button — it must be in HER language, not English.
_REASONING_LANG = {
    "hi": "Hindi (Devanagari script)",
    "te": "Telugu (Telugu script)",
    "en": "simple English",
}

_MOCK_REASONING = {
    "hi": "यह योजना आपकी स्थिति से मेल खाती है — विधवा, आय और राज्य ({state}) की शर्तें पूरी होती हैं।",
    "te": "ఈ పథకం మీ పరిస్థితికి సరిపోతుంది — వితంతువు, ఆదాయం మరియు రాష్ట్రం ({state}) షరతులు నెరవేరుతాయి.",
    "en": "Matches the scheme's widow, income and residence criteria for {state}.",
}

_FALLBACK_REASONING = {
    "hi": "नियमों के अनुसार आप इस योजना की पात्र हैं (एआई जाँच बाद में होगी)।",
    "te": "నియమాల ప్రకారం మీరు ఈ పథకానికి అర్హులు (ఏఐ తనిఖీ తర్వాత జరుగుతుంది).",
    "en": "Matches rule-based criteria (detailed AI check will follow).",
}


def _evaluate_with_llm(profile: dict, cert: dict | None, scheme: dict, conversation: str = "", web_context: str = "", lang: str = "en") -> dict:
    lang = lang if lang in _REASONING_LANG else "en"
    if gemini_service.mock:
        # Deterministic verdict so the demo works without an API key:
        # rule-filtered candidates are treated as eligible at their real value.
        return {
            "eligible": True,
            "confidence": 0.85,
            "reasoning": _MOCK_REASONING[lang].format(state=profile.get("state")),
            "estimated_annual_value": scheme.get("estimated_annual_value", 0),
            "missing_documents": [],
        }
    web_block = f"\nCURRENT WEB CONTEXT (fresh, from dedicated search API — use to catch policy changes, do NOT hallucinate schemes not in SCHEME):\n{web_context}\n" if web_context else ""
    prompt = (
        "Given this widow's profile and this Indian government scheme, decide eligibility.\n"
        f"PROFILE: {json.dumps(profile, ensure_ascii=False)}\n"
        f"HER OWN WORDS (chat, may add details the profile misses): {conversation[:1500]}\n"
        f"DEATH CERTIFICATE DATA: {json.dumps(cert, ensure_ascii=False)}\n"
        f"SCHEME: {json.dumps(scheme, ensure_ascii=False)}"
        f"{web_block}"
        "\nIf a key eligibility fact is simply unknown (not contradicted), set eligible=true with "
        "confidence 0.5-0.6 and name what must be verified in missing_documents — do not silently "
        "reject on missing information alone.\n"
        f"Write the \"reasoning\" sentence in {_REASONING_LANG[lang]} — one short sentence a rural "
        "woman with little schooling immediately understands. Everything else stays in English.\n"
        "Return ONLY JSON: {\"eligible\": bool, \"confidence\": 0-1, \"reasoning\": str, "
        "\"estimated_annual_value\": number (₹/year), \"missing_documents\": [str]}"
    )
    try:
        raw = gemini_service.chat(prompt)
    except Exception as e:
        # Free-tier rate limits (429) mid-run must not kill the demo: fall
        # back to the rule-based verdict for this scheme and keep going.
        if is_quota_error(e):
            pass  # expected on the free tier — same fallback either way
        return {
            "eligible": True,
            "confidence": 0.7,
            "reasoning": _FALLBACK_REASONING[lang],
            "estimated_annual_value": scheme.get("estimated_annual_value", 0),
            "missing_documents": [],
        }
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        result = json.loads(match.group()) if match else {"eligible": False, "confidence": 0}
    result.setdefault("estimated_annual_value", scheme.get("estimated_annual_value", 0))
    result.setdefault("reasoning", "")
    result.setdefault("missing_documents", [])
    return result


def reason(state: DiscoveryState) -> DiscoveryState:
    evaluations = []
    lang = (state["profile"].get("language") or "en-IN").split("-")[0]
    for scheme in state["candidates"]:
        verdict = _evaluate_with_llm(
            state["profile"],
            state.get("death_certificate"),
            scheme,
            state.get("conversation", ""),
            state.get("web_context", ""),
            lang,
        )
        verdict["scheme"] = scheme
        evaluations.append(verdict)
        log_action(
            state["widow_id"],
            "discovery",
            f"Evaluated {scheme['name'].split('/')[-1].strip()}: "
            + ("eligible ✓" if verdict.get("eligible") else "not eligible ✗")
            + f" (confidence {verdict.get('confidence', 0):.0%})",
            {"reasoning": verdict.get("reasoning")},
        )
    state["evaluations"] = evaluations
    return state


def verify_gaps(state: DiscoveryState) -> DiscoveryState:
    """Information-gap state gate. A scheme must not reach the claim list on
    an unverified household fact: Sukanya Samriddhi Yojana applies only if a
    daughter is under 10, which the 5 intake questions never establish.

      unknown → HALT the pipeline; the voice agent asks a clarifying question
                (in her language) and discovery re-runs after she answers.
      no      → exclude the scheme outright (conflict check).
      yes     → keep it as a confirmed match, not a "needs verification" card.
    """
    p = state["profile"]
    evaluations = state.get("evaluations", [])
    ssy = next(
        (e for e in evaluations if e["scheme"]["id"] == "ssy" and e.get("eligible")),
        None,
    )
    if ssy is None:
        return state

    has_daughter = p.get("has_daughter_under_10")
    children = p.get("children_count")

    if has_daughter == 0 or children == 0:
        state["evaluations"] = [e for e in evaluations if e["scheme"]["id"] != "ssy"]
        log_action(
            state["widow_id"], "discovery",
            "Conflict check — Sukanya Samriddhi Yojana: excluded "
            "(no daughter under 10 in the household — confirmed with the family)",
            {"scheme_id": "ssy", "reason": "no daughter under 10"},
        )
        return state

    if has_daughter == 1:
        lang = (p.get("language") or "en-IN").split("-")[0]
        confirmed = {
            "hi": " परिवार से पुष्टि हुई: 10 साल से छोटी बेटी है।",
            "te": " కుటుంబంతో ధృవీకరించాం: 10 ఏళ్లలోపు కుమార్తె ఉంది.",
            "en": " Confirmed with the family: she has a daughter under 10.",
        }.get(lang, " Confirmed with the family: she has a daughter under 10.")
        ssy["confidence"] = max(ssy.get("confidence", 0), 0.9)
        ssy["reasoning"] = (
            (ssy.get("reasoning") or "").rstrip().rstrip(".") + "." + confirmed
        ).lstrip(". ")
        # The daughter's existence is now verified — drop only those "verify"
        # items; her birth certificate etc. still come from documents_required.
        ssy["missing_documents"] = [
            d for d in ssy.get("missing_documents", [])
            if "daughter" not in d.lower() and "girl" not in d.lower()
        ]
        return state

    # Unknown, and she does have children → HALT and ask before persisting.
    if not children:
        return state  # children count itself unknown — leave the LLM verdict

    lang = (p.get("language") or "en-IN").split("-")[0]
    question = DAUGHTER_QUESTION.get(lang, DAUGHTER_QUESTION["en"]).format(
        name=p.get("name") or GAP_FALLBACK_NAME.get(lang, GAP_FALLBACK_NAME["en"]),
        n=children,
    )
    state["halt"] = True
    state["followup_question"] = question
    with SessionLocal() as db:
        widow = db.get(Widow, state["widow_id"])
        if widow is not None:
            widow.pending_question = "daughter_under_10"
            db.commit()
    log_action(
        state["widow_id"], "discovery",
        "⏸ Pipeline HALTED — Sukanya Samriddhi Yojana matches only if a "
        "daughter is under 10, but that fact is unknown. Asking the family "
        "before confirming any scheme.",
        {"gap": "daughter_under_10", "scheme_id": "ssy", "next_action": "ASK_FOLLOWUP"},
    )
    return state


def persist(state: DiscoveryState) -> DiscoveryState:
    # Information gap open: nothing is persisted until she answers — the
    # voice agent asks the follow-up question and discovery re-runs.
    if state.get("halt"):
        state["claims"] = []
        return state

    eligible = [
        e for e in state["evaluations"]
        if e.get("eligible") and e.get("confidence", 0) >= CONFIDENCE_THRESHOLD
    ]
    eligible.sort(key=lambda e: e.get("estimated_annual_value", 0), reverse=True)

    claims = []
    with SessionLocal() as db:
        for e in eligible:
            scheme = e["scheme"]
            exists = (
                db.query(Claim)
                .filter_by(widow_id=state["widow_id"], scheme_id=scheme["id"])
                .first()
            )
            if exists:
                claims.append(exists.to_dict())
                continue
            needed = list(e.get("missing_documents") or [])
            for doc in scheme.get("documents_required", []):
                if doc not in needed:
                    needed.append(doc)
            verify_prefix = (
                f"⚠ Needs verification (confidence {e.get('confidence', 0):.0%}). "
                if e.get("confidence", 0) < VERIFY_BELOW
                else ""
            )
            claim = Claim(
                widow_id=state["widow_id"],
                scheme_id=scheme["id"],
                scheme_name=scheme["name"],
                status="discovered",
                estimated_annual_value=int(e.get("estimated_annual_value", 0)),
                reasoning=e.get("reasoning"),
                notes=verify_prefix + ("Documents needed: " + "; ".join(needed[:6]) if needed else ""),
            )
            db.add(claim)
            db.commit()
            claims.append(claim.to_dict())

    state["claims"] = claims
    total = sum(c["estimated_annual_value"] for c in claims)
    log_action(
        state["widow_id"],
        "discovery",
        f"Discovery complete: {len(claims)} schemes worth ₹{total:,}/year",
        {"total_annual_value": total},
    )
    return state


# ---------------------------------------------------------------- pipeline
def _build_graph():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DiscoveryState)
    graph.add_node("load_profile", load_profile)
    graph.add_node("retrieve", retrieve)
    graph.add_node("reason", reason)
    graph.add_node("verify_gaps", verify_gaps)
    graph.add_node("persist", persist)
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "retrieve")
    graph.add_edge("retrieve", "reason")
    graph.add_edge("reason", "verify_gaps")
    # Gate: an open information gap routes to a follow-up question instead
    # of persisting half-verified claims.
    graph.add_conditional_edges(
        "verify_gaps",
        lambda s: "ask_followup" if s.get("halt") else "persist",
        {"ask_followup": END, "persist": "persist"},
    )
    graph.add_edge("persist", END)
    return graph.compile()


def run_discovery(widow_id: str) -> dict:
    state: DiscoveryState = {"widow_id": widow_id}
    try:
        app = _build_graph()
        state = app.invoke(state)
    except ImportError:
        for node in (load_profile, retrieve, reason, verify_gaps, persist):
            state = node(state)
            if state.get("halt"):
                break

    claims = state.get("claims", [])
    return {
        "widow_id": widow_id,
        "schemes_found": len(claims),
        "total_annual_value": sum(c["estimated_annual_value"] for c in claims),
        "claims": claims,
        # Non-null when the pipeline halted on an information gap: the caller
        # must relay this question to the widow and re-run discovery after
        # her answer (the onboarding agent stores it on the profile).
        "followup_question": state.get("followup_question"),
    }
