"""SchemeRAG — semantic search over the scheme knowledge base.

Uses ChromaDB (persisted at backend/data/chroma) when available; falls back to
a plain in-memory cosine-similarity index if chromadb isn't installed, so the
app still runs in constrained environments.
"""

import json
import math
import os

from services.gemini import gemini_service

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEMES_PATH = os.path.join(DATA_DIR, "schemes.json")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class SchemeRAG:
    def __init__(self) -> None:
        with open(SCHEMES_PATH, encoding="utf-8") as f:
            self.schemes: list[dict] = json.load(f)
        self.by_id = {s["id"]: s for s in self.schemes}
        self._collection = None
        self._fallback_index: list[tuple[str, list[float]]] = []
        self._build_index()

    def _doc_text(self, scheme: dict) -> str:
        return " | ".join(
            [
                scheme["name"],
                scheme["state"],
                " ".join(scheme["eligibility"]),
                " ".join(scheme["documents_required"]),
            ]
        )

    def _build_index(self) -> None:
        # Decide real-vs-mock embeddings once, up front, so the whole index is
        # built in a single consistent space even if quota is exhausted.
        gemini_service.prepare_embeddings()
        try:
            import chromadb

            client = chromadb.PersistentClient(path=CHROMA_PATH)
            # Collection name is tied to the embedding space (mock vs real
            # model) so switching modes rebuilds instead of mixing vectors.
            self._collection = client.get_or_create_collection(
                f"schemes-{gemini_service.index_tag}"
            )
            existing = set(self._collection.get()["ids"])
            missing = [s for s in self.schemes if s["id"] not in existing]
            if missing:
                self._collection.add(
                    ids=[s["id"] for s in missing],
                    embeddings=[gemini_service.embed(self._doc_text(s)) for s in missing],
                    documents=[self._doc_text(s) for s in missing],
                )
        except Exception:
            # Fallback: naive in-memory index (still deterministic + fast for 15 docs)
            self._collection = None
            self._fallback_index = [
                (s["id"], gemini_service.embed(self._doc_text(s))) for s in self.schemes
            ]

    # ---------------------------------------------------------------- search
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        q_emb = gemini_service.embed(query)
        if self._collection is not None:
            res = self._collection.query(query_embeddings=[q_emb], n_results=min(top_k, len(self.schemes)))
            ids = res["ids"][0]
        else:
            scored = sorted(
                self._fallback_index, key=lambda pair: _cosine(q_emb, pair[1]), reverse=True
            )
            ids = [sid for sid, _ in scored[:top_k]]
        return [self.by_id[i] for i in ids]

    # Schemes tied to what the husband did for a living. If his occupation is
    # known and doesn't match, the scheme is filtered out before any LLM call.
    OCCUPATION_GATES = {
        "central-family-pension": {"government job"},
        "compassionate-appointment": {"government job"},
        "bocw-death-benefit": {"laborer"},
        "ts-rythu-bima": {"farmer"},
        "eps95-widow": {"government job", "private job"},  # needs formal-sector EPF membership
    }

    # Gates only fire for these canonical categories. Free-text occupations
    # ("teacher", "tailor") are ambiguous — leave those to the LLM to judge.
    KNOWN_OCCUPATIONS = {"farmer", "laborer", "government job", "private job", "driver", "shopkeeper"}

    # --- Scheme taxonomy for the eligibility / conflict engine -------------
    # BPL social-welfare pensions & benefits: exclude families of government
    # employees and taxpayers; income-ceiling gated.
    BPL_WELFARE = {
        "ignwps", "nfbs", "aaby", "ap-ntr-bharosa", "up-widow-pension",
        "bihar-lsspy", "mp-kalyani-pension", "raj-ekal-nari", "mh-sgnay",
        "ka-vidhava-vetana",
    }
    # State widow pensions (a subset of BPL welfare) — the central IGNWPS
    # component is merged into these, so they are mutually exclusive with IGNWPS.
    STATE_WIDOW_PENSION = {
        "ap-ntr-bharosa", "up-widow-pension", "bihar-lsspy", "mp-kalyani-pension",
        "raj-ekal-nari", "mh-sgnay", "ka-vidhava-vetana",
    }
    GOVT_EMPLOYEE_SCHEMES = {"central-family-pension", "compassionate-appointment"}
    # Schemes that are means/BPL-tested beyond the welfare pensions above.
    POOR_HOUSEHOLD_SCHEMES = {"pmuy", "pmjay"}
    BPL_INCOME_CEILING = 15000  # ₹/month, rough upper bound for welfare eligibility

    @staticmethod
    def employment_sector(occupation: str) -> str:
        o = (occupation or "").lower()
        if "government" in o or "sarkari" in o or "teacher" in o or "clerk" in o:
            return "government"
        if "private" in o or "company" in o or "factory" in o:
            return "private"
        if "farmer" in o or "kisan" in o:
            return "farmer"
        if "labor" in o or "labour" in o or "mazdoor" in o or "construction" in o:
            return "laborer"
        if "driver" in o or "shop" in o or "gig" in o or "vendor" in o:
            return "unorganized"
        return "unknown"

    def screen_eligibility(self, profile: dict, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
        """The conflict & disqualification engine. Returns (eligible, excluded)
        where each excluded item is {"scheme":..., "reason":...}. Encodes the
        real administrative rules: government employees are excluded from BPL
        welfare and EPS-95; state widow pensions subsume IGNWPS; income ceilings;
        occupation-specific schemes."""
        state = (profile.get("state") or "").strip().lower()
        age = profile.get("age")
        income = profile.get("monthly_income")
        occ = (profile.get("husband_occupation") or "").strip().lower()
        sector = self.employment_sector(occ)

        def base_reason(s: dict) -> str | None:
            """All exclusion rules EXCEPT the IGNWPS-merge (needs a 2nd pass)."""
            sid = s["id"]
            # 1. Wrong state
            if s["state"] != "central" and state and s["state"].lower() != state:
                return "for a different state"
            # 2. Employment-sector conflicts (the big one)
            if sector == "government":
                if sid in self.BPL_WELFARE:
                    return "families of government employees are excluded from BPL social-welfare pensions"
                if sid == "eps95-widow":
                    return "government staff are under State/NPS pension, not EPFO/EPS-95"
                if sid in self.POOR_HOUSEHOLD_SCHEMES:
                    return "targets SECC/BPL poor households, not government-employee families"
            elif sector in ("farmer", "laborer", "unorganized", "private"):
                if sid in self.GOVT_EMPLOYEE_SCHEMES:
                    return "only for families of government employees"
                if sid == "eps95-widow" and sector != "private":
                    return "EPS-95 is for EPF-registered (organized private-sector) workers"
            # 3. Occupation-specific schemes needing the right occupation
            gate = self.OCCUPATION_GATES.get(sid)
            if gate and occ in self.KNOWN_OCCUPATIONS and occ not in gate:
                return "requires a different occupation of the deceased"
            # 4. Income ceiling for BPL welfare
            if sid in self.BPL_WELFARE and income and income > self.BPL_INCOME_CEILING:
                return f"family income ₹{income:,}/month is above the BPL welfare ceiling"
            # 5. Age gates
            if age is not None:
                if sid == "ignwps" and age < 40:
                    return "IGNWPS is for widows aged 40+"
                if sid == "pmvvy" and age < 60:
                    return "PMVVY is for citizens aged 60+"
                if sid == "bihar-lsspy" and age >= 40:
                    return "this slab is for widows aged 18–39"
            return None

        reasons = {s["id"]: base_reason(s) for s in candidates}

        # 2nd pass: IGNWPS is merged into the state widow pension ONLY when she
        # actually qualifies for that state pension (it passed all base rules).
        state_wp_eligible = any(
            s["id"] in self.STATE_WIDOW_PENSION
            and s["state"].lower() == state
            and reasons[s["id"]] is None
            for s in candidates
        )
        if state_wp_eligible and reasons.get("ignwps") is None:
            reasons["ignwps"] = "merged into the state widow pension — not paid separately"

        eligible, excluded = [], []
        for s in candidates:
            r = reasons[s["id"]]
            if r:
                excluded.append({"scheme": s, "reason": r})
            else:
                eligible.append(s)
        return eligible, excluded

    # ------------------------------------------------------ profile filtering
    def filter_by_profile(self, profile: dict, candidates: list[dict] | None = None) -> list[dict]:
        """Rule-based post-filter on top of semantic search."""
        pool = candidates if candidates is not None else self.schemes
        state = (profile.get("state") or "").strip().lower()
        age = profile.get("age")
        occupation = (profile.get("husband_occupation") or "").strip().lower()
        results = []
        for s in pool:
            # State filter: keep central schemes + the widow's own state
            if s["state"] != "central" and state and s["state"].lower() != state:
                continue
            # Occupation gate (only when the occupation is a known category)
            gate = self.OCCUPATION_GATES.get(s["id"])
            if gate and occupation in self.KNOWN_OCCUPATIONS and occupation not in gate:
                continue
            # Cheap age gates for the age-bound schemes
            if age is not None:
                if s["id"] == "ignwps" and not (40 <= age):
                    continue
                if s["id"] == "pmvvy" and age < 60:
                    continue
                if s["id"] == "bihar-lsspy" and age >= 40:
                    continue
            results.append(s)
        return results


scheme_rag = SchemeRAG()
