# WhatsApp Channel — Setup Guide

Pension Saathi can run inside WhatsApp: a widow chats with the same Saathi by
sending text, **voice notes**, or **photos of documents** on WhatsApp, and gets
replies back as text and voice notes. The agent logic is identical to the web
app — it just runs on the server.

> The code is complete and ships in the repo. To go live you need three things
> that only you can provide (below). Until then the server runs fine; WhatsApp
> and voice calls are simply logged and skipped.

## What you need

1. **A public HTTPS URL** for the backend (deploy to Render, then your webhook is
   `https://your-app.onrender.com/whatsapp/webhook`).
2. **WhatsApp Business Platform access** (free to start) from
   https://developers.facebook.com → create an app → add "WhatsApp" → get:
   - a **permanent access token** → `WHATSAPP_TOKEN`
   - the **phone number ID** → `WHATSAPP_PHONE_NUMBER_ID`
   - choose any **verify token** string → `WHATSAPP_VERIFY_TOKEN`
3. **A voice service key** (for voice notes) — either:
   - **ElevenLabs** (`ELEVENLABS_API_KEY`) — most natural voices, or
   - **Sarvam AI** (`SARVAM_API_KEY`) — best for Indian languages (Telugu/Hindi).

Put these in `backend/.env` (see `.env.example`).

## How to connect it

1. Deploy the backend (it already exposes `/whatsapp/webhook`).
2. In the Meta app dashboard → WhatsApp → Configuration → set the **Callback URL**
   to `https://your-app/whatsapp/webhook` and the **Verify token** to the same
   string you put in `WHATSAPP_VERIFY_TOKEN`. Meta will call the URL once; our
   `GET /whatsapp/webhook` answers the challenge automatically.
3. Subscribe to the **messages** field.
4. Send a WhatsApp message to your business number — Saathi replies.

## What works over WhatsApp

- **Text** → runs the 5-question onboarding, replies in her language.
- **Voice note** → transcribed (Speech-to-Text) → treated like text; replies also
  come back as a **voice note** (Text-to-Speech).
- **Photo of death certificate** → read with Gemini Vision → confirmed → discovery
  + filing run automatically → she gets a summary of her schemes (which were
  applied online, which need an office visit, with the plan).
- **More photos** (Aadhaar, passbook, ration card) → auto-classified → schemes
  re-checked → updated summary.

## Files involved

| File | Role |
|------|------|
| `backend/services/whatsapp_client.py` | Send text/audio, download incoming media (WhatsApp Cloud API) |
| `backend/services/voice.py` | Server-side Speech-to-Text and Text-to-Speech (ElevenLabs / Sarvam) |
| `backend/agents/whatsapp_handler.py` | Runs the onboarding → document → discovery → filing flow per phone number |
| `backend/main.py` | `GET/POST /whatsapp/webhook` endpoints |

## Note on the two voice systems

- **Web app** uses the browser's built-in speech (free, no server) — unchanged.
- **WhatsApp** uses server-side voice (ElevenLabs / Sarvam / Bhashini) because
  there is no browser inside WhatsApp.

Both share the exact same agent brain.
