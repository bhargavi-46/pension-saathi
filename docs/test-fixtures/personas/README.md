# Pension Saathi — Judge Testing Guide (Test Personas)

This folder contains **four ready-to-test widow personas**, each with a full set
of specimen documents (death certificate, Aadhaar, bank passbook) and the
**exact eligibility result you should expect**. Together they exercise every
branch of the eligibility engine — government-employee vs unorganized vs private
sector, four states, mutual-exclusivity, income ceilings, and occupation gating.

> ⚠️ **All documents are watermarked SPECIMENS with fictional data.** Aadhaar
> numbers intentionally begin with `1` (real ones never do) and IFSC codes use a
> `TEST` prefix, so they can never function as real documents. They exist only
> to test Pension Saathi's document reader.

## How to test any persona (2 minutes)

1. Open the app → **Try as Widow** (or `/chat`).
2. Click **⚙️ → New conversation (reset)** to start fresh.
3. Type `hello`, then answer the 5 questions using the persona's **onboarding
   answers** below (you can also answer in Hindi/Telugu — replies follow your
   language).
4. Tap **📎 → Death Certificate** and upload that persona's `death_certificate.jpg`.
5. Saathi runs discovery. Open the **Dashboard** (top bar) to watch the live
   **Agent Console** — you'll see each scheme evaluated and the **Conflict check**
   lines explaining every exclusion.
6. When Saathi asks, upload `aadhaar_widow.jpg` and `bank_passbook_widow.jpg`
   (and a ration card if you have one). Schemes that can be filed online flip to
   **Submitted**; the rest show a real **office action plan**.
7. Watch the dashboard for a few minutes — claims advance through their real
   administrative route (Ward Secretariat → WEA → MPDO, or DEO → Sub-Treasury,
   etc.), one hits a name-mismatch exception that Saathi auto-corrects, and a DBT
   payment lands — which Saathi announces back in the chat.

## The four personas at a glance

| Persona | State | Husband's work | Key point it proves |
|---|---|---|---|
| **K. Padma** | Andhra Pradesh | Government teacher | Govt employees get Family Pension + Compassionate job; **excluded** from BPL welfare & EPS-95 |
| **Rani Devi** | Bihar | Construction labourer | Unorganized worker gets BOCW + state welfare; state widow pension **absorbs** IGNWPS |
| **Lakshmi Bai** | Karnataka | Private-company driver | Private sector gets EPS-95 + state widow pension; **not** Family Pension |
| **Anitha** | Telangana | Farmer | Farmer gets Rythu Bima (₹5 L); IGNWPS applies (no TS widow-pension overlap) |

See each persona's own `README.md` for the exact onboarding answers and the full
expected/excluded scheme list.

## What to look for (the "wow" checklist for judges)

- **Discovery is real AI** — reasons about each scheme, not keyword matching.
- **Conflict engine** — the console shows *why* schemes are excluded (e.g. "NTR
  Bharosa: excluded — government employees are excluded from BPL social-welfare
  pensions").
- **Honest document gating** — nothing is "filed" until the required documents
  exist; office-only steps show a real visit plan (which office, what to bring).
- **Time-driven tracking** — claims move through real department desks over
  ~4 minutes; payouts only happen with Aadhaar + bank passbook on file.
- **Closed loop** — the DBT payment announced on the dashboard is also spoken to
  the widow in the chat, in her language.

*Simulated for the prototype: the passage of time and the government's internal
approval (compressed from weeks to minutes). Never simulated: the eligibility
logic, document reading, or the outcome — a payout requires the real documents.*
