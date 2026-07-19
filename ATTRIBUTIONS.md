# Attributions

Pension Saathi is built entirely on free and open-source software. This file
lists every direct dependency, notable transitive dependencies, and the public
data sources used for the scheme knowledge base.

## Direct backend dependencies (Python)

| Library | Version | License | Role in build | Source |
|---------|---------|---------|---------------|--------|
| FastAPI | ≥0.115 | MIT | REST + SSE API framework | https://github.com/fastapi/fastapi |
| Uvicorn | ≥0.30 | BSD-3-Clause | ASGI server | https://github.com/encode/uvicorn |
| SQLAlchemy | ≥2.0 | MIT | ORM over SQLite | https://github.com/sqlalchemy/sqlalchemy |
| Pydantic | ≥2.7 | MIT | Request/response validation | https://github.com/pydantic/pydantic |
| python-dotenv | ≥1.0 | BSD-3-Clause | Loads `.env` secrets | https://github.com/theskumar/python-dotenv |
| python-multipart | ≥0.0.9 | Apache-2.0 | Multipart form parsing (document upload) | https://github.com/Kludex/python-multipart |
| google-generativeai | ≥0.8 | Apache-2.0 | Gemini 2.0 Flash chat/vision/embeddings | https://github.com/google-gemini/generative-ai-python |
| ChromaDB | ≥0.5 | Apache-2.0 | Vector store for semantic scheme search | https://github.com/chroma-core/chroma |
| LangGraph | ≥0.2 | MIT | Discovery-agent pipeline orchestration | https://github.com/langchain-ai/langgraph |
| langchain-google-genai | ≥2.0 | MIT | LangChain ↔ Gemini bindings | https://github.com/langchain-ai/langchain-google |

## Direct frontend dependencies (npm)

| Library | Version | License | Role in build | Source |
|---------|---------|---------|---------------|--------|
| Next.js | 15.5.x | MIT | React framework (App Router) | https://github.com/vercel/next.js |
| React / React DOM | 19.1.x | MIT | UI runtime | https://github.com/facebook/react |
| Tailwind CSS | 4.x | MIT | Utility-first styling | https://github.com/tailwindlabs/tailwindcss |
| TypeScript | 5.x | Apache-2.0 | Type safety | https://github.com/microsoft/TypeScript |
| ESLint + eslint-config-next | 9.x | MIT | Linting | https://github.com/eslint/eslint |

## Notable transitive dependencies

| Library | License | Role |
|---------|---------|------|
| Starlette | BSD-3-Clause | ASGI toolkit under FastAPI (SSE StreamingResponse) |
| langchain-core | MIT | Base abstractions under LangGraph |
| onnxruntime | MIT | Embedding runtime bundled with ChromaDB |
| Geist & Playfair Display fonts | OFL-1.1 | Typography (via next/font) |

## AI providers

| Provider | Role | Notes |
|----------|------|-------|
| Google Gemini (2.5 Flash + embeddings) | Primary: document vision, eligibility reasoning, multilingual chat, semantic embeddings | via `google-generativeai` |
| Groq (Llama 3.3 70B + Llama 4 Scout vision) | Automatic fallback when Gemini is rate-limited | OpenAI-compatible REST API called with `requests`; Llama models are Meta, Llama Community License |

## Browser APIs

- **Web Speech API** (`webkitSpeechRecognition`, `speechSynthesis`) — built into Chrome/Edge, used for Hindi voice input/output. No external service.

## Data sources

The scheme knowledge base (`backend/data/schemes.json`) paraphrases publicly
available information about real Indian government schemes, for demonstration
purposes only. Benefit amounts and criteria change; always verify on the
official portals:

- https://nsap.nic.in — National Social Assistance Programme (IGNWPS, NFBS)
- https://www.myscheme.gov.in — Unified scheme discovery portal
- https://pmjay.gov.in — Ayushman Bharat PM-JAY
- https://www.pmuy.gov.in — PM Ujjwala Yojana
- https://www.jansuraksha.gov.in — PMJJBY / PMSBY
- https://www.epfindia.gov.in — EPS-95 widow pension
- https://licindia.in — PMVVY, Aam Aadmi Bima Yojana
- https://sspy-up.gov.in — UP pension portal
- https://serviceonline.bihar.gov.in — Bihar RTPS
- https://socialsecurity.mp.gov.in — MP pension portal
- https://ssp.rajasthan.gov.in — Rajasthan social security pensions
- https://aaplesarkar.mahaonline.gov.in — Maharashtra services
- https://sevasindhu.karnataka.gov.in — Karnataka services
- https://www.india.gov.in — Sukanya Samriddhi Yojana

## Design note

The playbook originally called for shadcn/ui; the final build uses hand-rolled
Tailwind components instead (fewer dependencies, same look), so no Radix UI
code ships in this repo.
