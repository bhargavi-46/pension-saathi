"""Seed the demo widow "Sunita Devi" so judges can open
/dashboard/demo-widow and immediately see a rich, believable state.

Runs on backend startup when the demo widow doesn't exist yet.
"""

import json
import random

from db import Claim, Conversation, Document, SessionLocal, Widow, log_action, utcnow
from services.rag import scheme_rag

DEMO_ID = "demo-widow"

DEMO_SCHEME_STATES = {
    "pmjjby-claim": "received",
    "ignwps": "tracking",
    "nfbs": "filed",
    "bihar-lsspy": "tracking",
    "pmjay": "received",
    "pmuy": "filed",
    "ssy": "discovered",
    "aaby": "filed",
}

DEMO_CHAT = [
    ("user", "नमस्ते"),
    ("agent", "नमस्ते बहन। मैं साथी हूँ — मैं आपको हर वह सरकारी योजना दिलाने में मदद करूँगी जिसकी आप हकदार हैं। सबसे पहले, आपका नाम क्या है?"),
    ("user", "मेरा नाम सुनीता देवी है"),
    ("agent", "धन्यवाद सुनीता देवी जी। आप किस राज्य और ज़िले में रहती हैं?"),
    ("user", "बिहार, गया ज़िला"),
    ("agent", "आपकी उम्र कितनी है, और आपके कितने बच्चे हैं?"),
    ("user", "42 साल, 2 बच्चे"),
    ("agent", "आपके पति का काम क्या था?"),
    ("user", "किसान थे"),
    ("agent", "अभी आपकी महीने की कमाई लगभग कितनी है?"),
    ("user", "3000 रुपये"),
    ("agent", "धन्यवाद सुनीता देवी जी। अब मैं आपके लिए हर योजना खोजूँगी जिसकी आप हकदार हैं।"),
]


def _tracking_id() -> str:
    import string

    return "PSA-2026-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def seed_if_needed() -> None:
    with SessionLocal() as db:
        if db.get(Widow, DEMO_ID) is not None:
            return

        widow = Widow(
            id=DEMO_ID,
            name="Sunita Devi",
            state="Bihar",
            district="Gaya",
            age=42,
            children_count=2,
            monthly_income=3000,
            husband_occupation="farmer",
            husband_death_date="2023-08-14",
            onboarding_step=5,
            language="hi-IN",
        )
        db.add(widow)

        for role, content in DEMO_CHAT:
            db.add(Conversation(widow_id=DEMO_ID, role=role, content=content))

        cert_data = {
            "deceased_name": "Ramesh Kumar",
            "date_of_death": "2023-08-14",
            "place_of_death": "Gaya, Bihar",
            "cause_of_death": None,
            "certificate_number": "DC-BR-2023-118842",
            "issuing_authority": "Registrar of Births & Deaths, Gaya Nagar Nigam",
        }
        db.add(
            Document(
                widow_id=DEMO_ID,
                doc_type="death_certificate",
                storage_path=None,
                extracted_data=json.dumps(cert_data, ensure_ascii=False),
            )
        )

        total = 0
        for scheme_id, status in DEMO_SCHEME_STATES.items():
            scheme = scheme_rag.by_id.get(scheme_id)
            if scheme is None:
                continue
            value = scheme["estimated_annual_value"]
            total += value
            db.add(
                Claim(
                    widow_id=DEMO_ID,
                    scheme_id=scheme_id,
                    scheme_name=scheme["name"],
                    status=status,
                    tracking_id=_tracking_id() if status != "discovered" else None,
                    filed_at=utcnow() if status != "discovered" else None,
                    estimated_annual_value=value,
                    reasoning="Widow, BPL-level income, Bihar resident — matches all criteria.",
                )
            )
        db.commit()

    log_action(DEMO_ID, "voice", "Onboarding complete for Sunita Devi (Bihar) — profile saved")
    log_action(DEMO_ID, "document", "Extracted data from death certificate — Ramesh Kumar",
               {"extracted": cert_data})
    log_action(DEMO_ID, "discovery",
               f"Discovery complete: {len(DEMO_SCHEME_STATES)} schemes worth ₹{total:,}/year",
               {"total_annual_value": total})
    log_action(DEMO_ID, "filing", "Filed 7 claims — tracking IDs issued")
    log_action(DEMO_ID, "tracking", "₹500 credited for IGNWPS — first payment received!")
