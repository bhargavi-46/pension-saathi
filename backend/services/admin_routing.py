"""Administrative routing — the real department chain each scheme's file
passes through, correct for the state. Used by the tracking simulation so the
agent console shows ground-truth offices (Ward Secretariat / DEO / STO / EPFO)
instead of generic North-Indian terms.

Sources: AP Grama/Ward Sachivalayam system, CCS Pension Rules routing via
DEO→Sub-Treasury, EPFO EPS-95 process, PMJJBY/AABY bank-insurer claim flow.
"""

from services.rag import scheme_rag

# --- State-specific social-welfare routing (widow pensions, NFBS, etc.) ------
WELFARE_ROUTE = {
    "Andhra Pradesh": [
        "Digital Assistant, {district} Ward/Village Secretariat — data entry & scrutiny",
        "Welfare & Education Assistant (WEA) — field verification & Aadhaar eKYC",
        "Mandal Parishad Development Officer (MPDO) — sanction",
        "District Collectorate / DRDA — approval",
    ],
    "Telangana": [
        "Panchayat/Ward Secretary — application scrutiny",
        "MeeSeva field verification & Aadhaar eKYC",
        "Mandal Development Officer (MDO) — sanction",
        "District Collectorate — approval",
    ],
    "Bihar": [
        "RTPS counter, Block office — application receipt",
        "Block Development Officer (BDO) — verification",
        "Sub-Divisional Officer (SDO) — sanction",
    ],
    "Uttar Pradesh": [
        "Jan Seva Kendra — application receipt",
        "Lekhpal / Tehsil — income & residence verification",
        "Sub-Divisional Magistrate (SDM) — sanction",
        "District Social Welfare Officer — approval",
    ],
    "default": [
        "Village/Ward Secretariat — application receipt",
        "field verification & Aadhaar eKYC",
        "Block/Mandal Development Officer — sanction",
        "District welfare office — approval",
    ],
}

# --- Government-employee statutory routes (education dept + treasury) --------
FAMILY_PENSION_ROUTE = [
    "Head of Office / DDO — pension papers (Form 14) prepared",
    "Mandal Educational Officer (MEO) — service record check",
    "Office of the District Educational Officer (DEO), {district} — service book verification",
    "Sub-Treasury Office (STO), {district} — PPO generation",
    "Bank — monthly family pension via DBT",
]
COMPASSIONATE_ROUTE = [
    "Mandal Educational Officer (MEO) — dossier submitted",
    "Office of the District Educational Officer (DEO), {district} — vacancy clearance",
    "District Selection Committee — compassionate appointment approval",
]
EPS95_ROUTE = [
    "EPFO Regional Office — Form 10-D scrutiny",
    "EPFO — member service verification",
    "EPFO — pension sanction (PPO issued)",
    "Bank — monthly EPS pension via DBT",
]
INSURANCE_ROUTE = [
    "Bank branch — claim-cum-discharge form forwarded to insurer",
    "LIC / insurer P&GS unit — claim scrutiny",
    "Insurer — claim amount settled to nominee's account",
]
HEALTH_ROUTE = [
    "Ayushman Mitra desk — Aadhaar e-KYC",
    "State Health Authority — beneficiary verification",
    "Ayushman (golden) card issued",
]


def route_for(scheme_id: str, state: str | None, district: str | None) -> list[str]:
    d = district or "your district"
    st = state or ""
    if scheme_id == "central-family-pension":
        route = FAMILY_PENSION_ROUTE
    elif scheme_id == "compassionate-appointment":
        route = COMPASSIONATE_ROUTE
    elif scheme_id == "eps95-widow":
        route = EPS95_ROUTE
    elif scheme_id in ("pmjjby-claim", "aaby"):
        route = INSURANCE_ROUTE
    elif scheme_id == "pmjay":
        route = HEALTH_ROUTE
    elif scheme_id in scheme_rag.BPL_WELFARE or scheme_id in scheme_rag.STATE_WIDOW_PENSION:
        route = WELFARE_ROUTE.get(st, WELFARE_ROUTE["default"])
    else:
        route = WELFARE_ROUTE.get(st, WELFARE_ROUTE["default"])
    return [step.format(district=d) for step in route]


def desk_at(scheme_id: str, state: str | None, district: str | None, fraction: float) -> str:
    """Pick the desk roughly `fraction` (0..1) of the way through the route."""
    route = route_for(scheme_id, state, district)
    if not route:
        return "the processing office"
    idx = min(int(fraction * len(route)), len(route) - 1)
    return route[idx]


def final_step(scheme_id: str, state: str | None, district: str | None) -> str:
    return route_for(scheme_id, state, district)[-1]


# --- Milestone timeline -----------------------------------------------------
# Real-world administrative milestones, with the demo-compressed minute at
# which each is reached (so a judge sees the file advance over ~4 minutes),
# and the real-world elapsed span we quote to the widow.
MILESTONES = [
    # (compressed_minute, status, label_template, real_world_when)
    (0.0, "filed", "received & digitally validated at {desk}", "within 48 hours"),
    (0.75, "tracking", "under verification at {desk}", "in 7–14 days"),
    (2.0, "tracking", "sanction in progress — {desk}", "in 21–30 days"),
    (4.0, "received", "approved — first DBT payment via {desk}", "in 30–45 days"),
]
PAYOUT_MILESTONE = len(MILESTONES) - 1


def milestone_index_for(elapsed_minutes: float) -> int:
    idx = 0
    for i, (minute, *_rest) in enumerate(MILESTONES):
        if elapsed_minutes >= minute:
            idx = i
    return idx


def milestone_desk(scheme_id: str, state: str | None, district: str | None, idx: int) -> str:
    fraction = idx / max(len(MILESTONES) - 1, 1)
    return desk_at(scheme_id, state, district, fraction)


def expected_timeline_text(scheme_id: str, state: str | None, district: str | None) -> str:
    """Honest, reality-based timeline shown to the widow when a claim is filed."""
    route = route_for(scheme_id, state, district)
    verify = MILESTONES[1][3]
    payout = MILESTONES[3][3]
    return (
        f"Filed. Expected: local verification {verify}, "
        f"first payment {payout} via {route[-1].split('—')[0].strip()}."
    )
