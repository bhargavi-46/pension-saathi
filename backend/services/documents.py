"""Document intelligence + realistic application planning.

Decides, per scheme, whether the widow can submit online now or must
physically visit an office — and produces an honest action plan (which office,
what to bring, what to obtain first). No fake bookings: the plan is guidance
the agent gives her, matching how these schemes actually work.
"""

# Documents she can provide by photographing something she already has.
# doc_type keys match what the upload dialog offers.
COLLECTABLE = {
    "death_certificate": ["death certificate"],
    "aadhaar": ["aadhaar", "aadhar"],
    "bank_passbook": ["bank passbook", "passbook", "bank account", "aadhaar-linked bank"],
    "ration_card": ["ration card", "rice card", "white ration", "bpl card"],
}

# Handled AT submission (form filled at the counter/portal, ID-derived, or a
# self-declaration) — these do NOT block an online application.
AUTO_HANDLED = [
    "claim form", "discharge", "self-declaration", "self declaration",
    "secc", "family id", "photograph", "photo", "age proof",
    "marriage proof / joint photo", "joint photo",
]

# Documents that must be OBTAINED (often in person) before applying, and where.
MUST_OBTAIN_HINTS = {
    "income certificate": "apply at your nearest MeeSeva / e-Seva / CSC centre",
    "caste certificate": "apply at your nearest MeeSeva / Tahsildar office",
    "service certificate": "request from your husband's former department (Head of Office / DDO)",
    "ppo": "request from your husband's department or pension-disbursing bank",
    "service book": "request from your husband's former department",
    "form 14": "collect from your husband's department or pensionersportal.gov.in",
    "form 10": "collect from the EPFO office or download from epfindia.gov.in",
    "uan": "obtain your husband's UAN/PF number from his old payslip or his employer",
    "pf": "obtain PF details from your husband's employer or the EPFO office",
    "aaby policy": "ask the agency that enrolled your husband (bank/NGO) for the AABY membership",
    "pmjjby premium": "check your husband's bank passbook for the ₹436 yearly PMJJBY debit",
    "marriage": "obtain a marriage certificate from your local municipal / gram panchayat office",
    "breadwinner": "get a certificate from the Village/Ward Secretary that your husband was the earner",
    "dependency certificate": "obtain from the Tahsildar / Village Secretariat",
    "educational certificate": "keep your own school/college certificates ready",
    "age proof": "any government ID showing your date of birth works",
    "photograph": "keep 2-3 passport-size photos ready",
    "discharge": "the bank/insurer provides the discharge receipt when you file",
    "claim form": "the office/bank gives you the claim form when you visit",
}

# Where she physically goes, by state, to lodge social-welfare applications.
STATE_OFFICE = {
    "Andhra Pradesh": "your nearest Village/Ward Secretariat (or MeeSeva centre)",
    "Telangana": "your nearest MeeSeva centre (or Village Secretariat)",
    "Bihar": "your Block office (RTPS counter)",
    "Uttar Pradesh": "your nearest Jan Seva Kendra / Block office",
    "Rajasthan": "your nearest e-Mitra kiosk",
    "Madhya Pradesh": "your Gram Panchayat / Janpad office",
    "Maharashtra": "your nearest Aaple Sarkar Seva Kendra / Tahsildar office",
    "Karnataka": "your nearest Nadakacheri (Atalji Janasnehi Kendra)",
}
DEFAULT_OFFICE = "your nearest Common Service Centre (CSC) / Gram Panchayat office"

# Schemes whose application goes through the husband's employer, not a welfare office.
EMPLOYER_ROUTED = {
    "central-family-pension": "your husband's former department office (Head of Office / DDO)",
    "compassionate-appointment": "your husband's former department office (Head of Office)",
    "eps95-widow": "the EPFO regional office (or via your husband's former employer)",
}


def _matches(doc_text: str, keywords: list[str]) -> bool:
    low = doc_text.lower()
    return any(k in low for k in keywords)


def classify_documents(required: list[str], docs_on_file: set[str]) -> dict:
    """Split a scheme's required documents into: already provided, still to
    upload (collectable by photo), auto-handled at submission (non-blocking),
    and to-obtain from an office (with where-to-get hints)."""
    have, to_upload, to_obtain = [], [], []
    for doc in required:
        collectable_type = None
        for dtype, kws in COLLECTABLE.items():
            if _matches(doc, kws):
                collectable_type = dtype
                break
        if collectable_type:
            if collectable_type in docs_on_file:
                have.append(doc)
            else:
                to_upload.append((doc, collectable_type))
        elif _matches(doc, AUTO_HANDLED):
            continue  # filled in at submission — not a blocker
        else:
            hint = next((h for key, h in MUST_OBTAIN_HINTS.items() if key in doc.lower()), None)
            to_obtain.append((doc, hint))
    return {"have": have, "to_upload": to_upload, "to_obtain": to_obtain}


def office_for(scheme_id: str, state: str | None) -> str:
    if scheme_id in EMPLOYER_ROUTED:
        return EMPLOYER_ROUTED[scheme_id]
    return STATE_OFFICE.get(state or "", DEFAULT_OFFICE)


def assess_claim(scheme: dict, docs_on_file: set[str], state: str | None) -> dict:
    """Decide the realistic status + next step for one scheme.

    Returns: {status, missing_uploads:[doc_type], action_plan:str}
      status ∈ {ready, needs_documents, action_needed}
    """
    required = scheme.get("documents_required", [])
    cls = classify_documents(required, docs_on_file)
    missing_upload_types = [dtype for _, dtype in cls["to_upload"]]

    # Anything that must be obtained from an office => physical action needed.
    if cls["to_obtain"]:
        office = office_for(scheme["id"], state)
        obtain_lines = []
        for doc, hint in cls["to_obtain"]:
            obtain_lines.append(f"• {doc}" + (f" — {hint}" if hint else ""))
        bring = [d for d, _ in cls["to_upload"]] + cls["have"]
        plan = (
            f"This scheme needs an in-person step. Visit {office}. "
            f"Documents to obtain first:\n" + "\n".join(obtain_lines)
        )
        if bring:
            plan += "\nBring with you: " + ", ".join(sorted(set(bring)))
        return {"status": "action_needed", "missing_uploads": missing_upload_types, "action_plan": plan}

    if missing_upload_types:
        return {
            "status": "needs_documents",
            "missing_uploads": missing_upload_types,
            "action_plan": "Please send photos of: "
            + ", ".join(dt.replace("_", " ") for dt in missing_upload_types),
        }

    return {
        "status": "ready",
        "missing_uploads": [],
        "action_plan": f"All documents ready — application prepared for {scheme.get('where_to_apply', 'the portal')}.",
    }
