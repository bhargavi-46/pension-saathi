"""Filing agent — files each discovered claim (mocked for the prototype).

Generates PSA tracking IDs, flips claims to `filed`, and schedules a
background simulator that progresses claims to `tracking`/`received` over the
next few seconds so the dashboard shows believable motion during a demo.
"""

import asyncio
import random
import string
from datetime import datetime, timedelta, timezone

from db import Claim, SessionLocal, Widow, has_payment_docs, log_action, uploaded_doc_types, utcnow
from services.admin_routing import expected_timeline_text
from services.documents import assess_claim
from services.rag import scheme_rag


def _tracking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"PSA-{datetime.now().year}-{suffix}"


def _short(name: str) -> str:
    return name.split("/")[-1].strip()


def prepare_and_submit(widow_id: str) -> dict:
    """The honest core: for every eligible claim, check the documents actually
    on file and decide its real status —
      • ready & online   → submit now (tracking ID issued)
      • needs_documents  → wait for her to upload photos she can provide
      • action_needed    → she must visit an office; we give the action plan
    Returns a summary incl. which documents to ask her for next.
    """
    docs_on_file = uploaded_doc_types(widow_id)
    with SessionLocal() as db:
        widow = db.get(Widow, widow_id)
        state = widow.state if widow else None
        # (Re)assess anything not already submitted/progressed.
        claims = (
            db.query(Claim)
            .filter(
                Claim.widow_id == widow_id,
                Claim.status.in_(["discovered", "needs_documents", "action_needed"]),
            )
            .all()
        )
        submitted, needs_docs, action_needed = [], [], []
        needed_upload_types: set[str] = set()
        # Per-scheme detail so the chat can ask an interactive, targeted
        # follow-up ("For <scheme> I still need <doc>") instead of a generic
        # combined list — the claim stays halted until she responds.
        pending_uploads: list[dict] = []

        for claim in claims:
            scheme = scheme_rag.by_id.get(claim.scheme_id)
            if not scheme:
                continue
            verdict = assess_claim(scheme, docs_on_file, state)
            claim.notes = verdict["action_plan"]
            needed_upload_types.update(verdict["missing_uploads"])
            if verdict["status"] == "needs_documents" and verdict["missing_uploads"]:
                pending_uploads.append({
                    "scheme": _short(claim.scheme_name),
                    "docs": verdict["missing_uploads"],
                })

            if verdict["status"] == "ready":
                claim.status = "filed"  # 'filed' = submitted into the tracking pipeline
                claim.tracking_id = _tracking_id()
                claim.filed_at = utcnow()
                submitted.append(claim.scheme_name)
                timeline = expected_timeline_text(claim.scheme_id, widow.state if widow else None,
                                                  widow.district if widow else None)
                log_action(
                    widow_id, "filing",
                    f"Submitted {_short(claim.scheme_name)} online — Tracking ID {claim.tracking_id}. {timeline}",
                    {"where": scheme.get("where_to_apply"), "timeline": timeline},
                )
            else:
                claim.status = verdict["status"]
                if verdict["status"] == "action_needed":
                    action_needed.append(claim.scheme_name)
                    log_action(
                        widow_id, "filing",
                        f"{_short(claim.scheme_name)} needs an in-person step — prepared an action plan",
                        {"plan": verdict["action_plan"]},
                    )
                else:
                    needs_docs.append(claim.scheme_name)
            db.commit()

    return {
        "submitted": len(submitted),
        "needs_documents": len(needs_docs),
        "action_needed": len(action_needed),
        "ask_for_uploads": sorted(needed_upload_types),
        "pending_uploads": pending_uploads,
    }


async def simulate_progress(widow_id: str) -> None:
    """Demo simulator: over ~5-15s, move some submitted claims forward through
    their real administrative route."""
    from services.admin_routing import desk_at, final_step

    await asyncio.sleep(random.uniform(5, 8))
    with SessionLocal() as db:
        widow = db.get(Widow, widow_id)
        state, district = (widow.state, widow.district) if widow else (None, None)
        filed = db.query(Claim).filter_by(widow_id=widow_id, status="filed").all()
        for claim in filed:
            claim.status = "tracking"
            db.commit()
            log_action(
                widow_id,
                "tracking",
                f"Checked status of {claim.tracking_id} — received at "
                f"{desk_at(claim.scheme_id, state, district, 0.0)}",
            )

    await asyncio.sleep(random.uniform(4, 7))
    with SessionLocal() as db:
        tracking = db.query(Claim).filter_by(widow_id=widow_id, status="tracking").all()
        tracking_ids = [c.id for c in tracking]
    if not tracking_ids:
        return
    if not has_payment_docs(widow_id):
        with SessionLocal() as db:
            claim = db.get(Claim, tracking_ids[0])
            log_action(
                widow_id,
                "tracking",
                f"{claim.tracking_id} approved in principle — payment ON HOLD: "
                "Aadhaar and bank passbook not yet provided",
            )
        return
    # Every submitted claim completes (staggered a few seconds apart), so the
    # dashboard's "Payments received" counter and the chat's per-payment
    # messages always agree — one distinct announcement per claim.
    for claim_id in tracking_ids:
        with SessionLocal() as db:
            claim = db.get(Claim, claim_id)
            if not claim or claim.status != "tracking":
                continue
            claim.status = "received"
            db.commit()
            scheme_short = claim.scheme_name.split("/")[-1].strip()
            if claim.scheme_id == "pmjay":
                log_action(
                    widow_id, "tracking",
                    f"Ayushman (golden) card ACTIVE for {claim.tracking_id} — "
                    "₹5,00,000/year cashless hospital cover now live",
                    {"health_cover": True, "tracking_id": claim.tracking_id},
                )
            else:
                monthly = max(claim.estimated_annual_value // 12, 300)
                log_action(
                    widow_id,
                    "tracking",
                    f"₹{monthly:,} credited via DBT for {scheme_short} "
                    f"({claim.tracking_id}) — first payment received!",
                    {"payment": monthly, "scheme": scheme_short, "tracking_id": claim.tracking_id},
                )
        await asyncio.sleep(random.uniform(3, 5))
