# Clinic LM — Documentation

## What this actually is

The tempting one-line description — "ChatGPT for doctors" — is wrong, and the code makes that clear. Clinic LM is a per-patient-case workspace where a clinician uploads whatever documentation they have (PDFs, a URL, pasted text), the app synthesizes it into a working case file, and then a panel of purpose-built clinical analysis tools can be run against that case. It runs entirely against a **locally-hosted LLM (Ollama)** — no cloud API calls for the model itself — which matters because it means patient data never has to leave the machine it's deployed on.

The throughline across the whole backend is a deliberate design philosophy: **wherever a real authoritative source exists — a drug interaction database, the ICD-11 registry, PubMed, a rare-disease ontology, a validated clinical scoring formula — use it, and only let the LLM handle the parts that genuinely require language understanding** (extracting structured facts from prose, synthesizing evidence, mapping free text to formal codes). The LLM is rarely the source of a clinical fact in this system; it's the thing that reads, extracts, retrieves, and writes up.

The clearest evidence of this is `clinical_analyzer.py` — the differential-diagnosis tool. It doesn't just ask the model "what could this be." It encodes an actual clinical-reasoning methodology as an enforced multi-step pipeline:

1. **Epidemiological prior first** — the model must state a condition's baseline prevalence for the patient's demographics *before* it's shown how symptoms match against it, specifically so it doesn't anchor on the presenting complaint.
2. **Bayesian update** — walk from that prior to a posterior (`high`/`medium`/`low`/`very_low`, deliberately never a hard percentage) based on which symptoms raise or lower probability.
3. **Active falsification** — for *every* candidate condition, including the leading one, the model is forced to produce at least one piece of evidence against it. If none genuinely exists, the schema requires it to say so explicitly rather than leaving the field empty — a direct guard against confirmation bias in the model's own output.
4. **Symptom gap analysis** — which hallmark symptoms of this condition are still unconfirmed or undenied.
5. **Next-best-discriminator** — instead of listing generic follow-up tests, it must name the *single* question or test that best separates the top two differentials, and justify why it beats the alternatives.
6. **Hedging is structurally enforced** — both the system prompt and the schema prohibit a definitive diagnosis; only "possible / likely / cannot be confirmed without X." This is built and labeled as decision support for a clinician, not an autonomous diagnostic authority.

What makes this enforceable rather than just prompt-and-hope is that every analysis service calls Ollama with `format=<PydanticModel>.model_json_schema()` — the model is constrained to emit JSON matching a strict schema (every evidence item must cite a real `source_type` and a specific `source_id`, never freeform text). That schema constraint is what turns an LLM call into something closer to a structured clinical tool than a chatbot.

Every other analysis tool follows the same shape — real source where one exists, LLM for the interpretive glue:

| Tool | Real source(s) it's grounded in | What the LLM actually does |
|---|---|---|
| Differential diagnosis | Patient docs, PubMed, shared medical knowledge base | Bayesian reasoning pipeline above |
| Drug interactions | RxNav (RxCUI resolution + interactions), OpenFDA (boxed warnings, adverse events) | Extracts/normalizes drug names, writes a PICO summary per interaction |
| Risk scores | Wells DVT, CHA₂DS₂-VASc, qSOFA, MELD/MELD-Na — real validated formulas | Only extracts the input parameters from the case text; the score itself is computed deterministically, not by the model |
| Rare disease matching | Orphanet / HPO (Human Phenotype Ontology) | Extracts symptoms, which are mapped to HPO IDs and matched against real disease data |
| ICD-11 mapping | WHO ICD-11 API | Generates search terms from extracted keywords |
| Literature review | PubMed | Formulates search queries, grades returned articles A–D by evidence quality |
| Guidelines conformance | NLM clinical guidelines, PubMed Bookshelf | Compares documented management against retrieved guideline text |
| Contradiction detector | The uploaded documents themselves | Finds conflicting claims within one document and across documents |
| Document drafter | The case documentation | Generates a referral letter, discharge summary, and case write-up |

---

## Architecture

```
Browser
  │  (port 5173)
  ▼
Vite Dev Server (React 18 + TypeScript) ──proxies /api──▶ FastAPI Backend (port 8000)
                                                                │
                                          ┌─────────────┬──────┴──────┬─────────────┐
                                          ▼             ▼             ▼             ▼
                                     PostgreSQL      MongoDB      ChromaDB       Ollama
                                     (identity,    (case content, (two on-disk  (LLM, on
                                      sessions)      results)      vector stores)  host GPU)
```

**A clinical-analysis request, end to end:**
1. Browser calls e.g. `POST /api/notebooks/{id}/analyze` with the `session_id` cookie.
2. FastAPI resolves the user by joining `sessions` → `users` in Postgres (`dependencies.get_current_user`).
3. The service loads the case's `documentation` field from MongoDB.
4. A biomedical NER model (`d4data/biomedical-ner-all`) extracts clinical keywords from it.
5. Relevant chunks are pulled from the per-notebook vector index and/or the shared medical knowledge base (both ChromaDB).
6. A structured prompt is sent to Ollama with a Pydantic schema as the output contract.
7. Real external medical APIs are queried in parallel where relevant (PubMed, RxNav, OpenFDA, ICD-11, Orphadata, NLM), via a thread pool.
8. The result is written back onto the notebook's MongoDB document and returned as JSON.

**On backend startup** (`main.py` lifespan), the app deliberately front-loads the slow parts — connecting to Postgres, migrating schema, creating Mongo indexes, and pre-loading the NER model and the RAG embedding model onto the GPU — so the *first* real user request isn't the one that eats a cold-start penalty. It also auto-builds the shared medical knowledge base's vector index if one doesn't exist yet but source files are already on disk.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript 5, Vite 5, React Router 6, React Markdown, Sass |
| Backend | Python 3.11, FastAPI 0.115, Uvicorn, Pydantic v2 |
| Relational store | PostgreSQL 16 — identity & sessions only |
| Document store | MongoDB 7 — case content & analysis results |
| Vector stores | ChromaDB, embedded on disk (two independent collections, see below) |
| LLM | Ollama, `qwen2.5:7b` by default, fully local |
| NER | `d4data/biomedical-ner-all` (HuggingFace Transformers) |
| Retrieval embeddings | MedCPT (shared knowledge base) + a HuggingFace transformer (per-notebook chunks) |
| Document ingestion | LiteParse + Tesseract OCR |
| Email | Gmail SMTP (OTP delivery) |
| Infra | Docker Compose |

---

## Repository Structure

```
clinic-lm/
├── docker-compose.yml
├── .env                          # secrets & config, gitignored
├── backend/
│   ├── main.py                    # FastAPI app, startup preload, logging, global exception handler
│   ├── config.py                  # env var loading
│   ├── dependencies.py            # get_current_user / require_admin
│   ├── db/postgres.py             # connection pool + schema migration
│   ├── db/mongo.py                # Mongo client + index init
│   ├── models/roles.py            # Role enum + ROLE_DEFINITIONS
│   ├── routers/
│   │   ├── auth.py                 # OTP login/registration
│   │   ├── users.py                 # profile + admin user management
│   │   ├── notebooks.py             # case CRUD + every analysis endpoint
│   │   └── rag_docs.py              # admin-managed shared knowledge base
│   ├── services/                   # one module per capability — see table above + below
│   ├── external/                   # thin clients for PubMed, RxNav, OpenFDA, ICD-11, Orphadata, NLM, DuckDuckGo
│   ├── utils/email.py              # Gmail SMTP sender
│   ├── notebook_rag_db/            # ChromaDB: one collection per notebook UUID
│   ├── medcpt_db/                  # ChromaDB: single shared "medical_docs" collection
│   └── rag_docs/                   # raw files backing the shared knowledge base
└── frontend/src/
    ├── App.tsx                     # routing + auth gate
    ├── context/UserContext.tsx     # session state
    ├── pages/                      # AuthPage, NotebooksPage, NotebookPage, UsersPage, RagDocsPage
    └── components/                 # SourcesPanel, ChatPanel, ToolsPanel, one modal per analysis tool
```

### Backend services, by role

- **Case pipeline**: `ingestion.py` (PDF/URL/text → text), `generation.py` (LLM writes title/summary/documentation from sources), `anonymizer.py` (optional PHI/PII stripping on upload), `notebook_rag.py` (chunks + embeds sources into a per-case vector index).
- **Analysis tools**: `clinical_analyzer.py`, `interaction_checker.py`, `icd11_tree.py`, `literature_review.py`, `risk_analyser.py`, `rare_disease.py` + `rare_disease_triangulator.py`, `contradiction_detector.py`, `guidelines_conformance.py`, `document_drafter.py`, `chat_bot.py` (streaming chat over the case).
- **Shared infrastructure**: `extract_keywords.py` (NER), `rag_retriever.py` (MedCPT retrieval over the shared knowledge base), `rag_docs.py` (admin CRUD + reindex for that shared base), `data_model.py` (every Pydantic schema used as an Ollama structured-output contract).

---

## Running It

```bash
cp .env.example .env      # fill in DB creds, Gmail app password, ICD-11 OAuth creds, etc.
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

Prerequisites beyond Docker: Ollama running on the **host** (not containerized — the backend reaches it via `host.docker.internal`), with a model pulled (`ollama pull qwen2.5:7b`), and a GPU strongly recommended — the NER model and both RAG embedders benefit from it, and CPU inference is slow (30–60s per analysis call).

First admin: register through the UI, then
```sql
UPDATE users SET role_id = 3 WHERE email = 'your@email.com';
```

---

## Authentication

Passwordless, OTP-by-email — no password is ever stored.

```
POST /auth/request-otp {email}
  registered   → OTP sent            → { status: "otp_sent" }
  unregistered → nothing sent yet    → { status: "registration_required" }
                                          → POST /auth/register {email, name} creates the user (role=Free), sends OTP

POST /auth/verify-otp {email, otp}
  → checks 10-minute expiry + single-use
  → creates a 30-day session row in Postgres
  → sets an httponly, samesite=lax `session_id` cookie
```

Every protected route depends on `get_current_user` (401 if the cookie is missing/expired) or `require_admin` (403 if `role_id != Role.ADMIN`), both in `backend/dependencies.py`. Notably, `POST /auth/logout` only clears the cookie — it does **not** delete the session row, so a captured cookie stays valid until its 30-day expiry (see Known Constraints).

---

## Data Model

Three stores, each used for what it's actually good at:

**PostgreSQL** — identity and session bookkeeping only: `roles`, `users`, `otps`, `sessions`, and a `notebooks` table holding just case metadata (title, owner, source titles). Schema is created and migrated automatically on every boot (`ADD COLUMN IF NOT EXISTS`, safe to run repeatedly).

**MongoDB** — the actual case content, one document per notebook in `notebook_content`:
```json
{
  "notebook_id": "uuid", "user_id": "uuid",
  "sources": [{ "id", "type": "pdf|url|text", "name", "content" }],
  "documentation": "markdown synthesized from all sources",
  "summary": "short plain-text summary",
  "clinical_analysis": {}, "drug_interactions": {}, "icd11": {}, "literature": {},
  "risk": {}, "rare_diseases": {}, "contradictions": {}, "guidelines": {}, "drafts": {},
  "chat_history": [{ "role", "content" }]
}
```
Each analysis tool writes its result under its own key. Re-running a tool **overwrites** the previous result — there is no history of past runs.

**ChromaDB** (embedded, on disk, no separate server) — two independent stores:
- `notebook_rag_db/` — one collection per notebook, built automatically as sources are uploaded, deleted when the notebook is deleted.
- `medcpt_db/` — a single shared `medical_docs` collection, curated by admins (see below), used across *all* cases as a reference knowledge base.

---

## The Admin Medical Knowledge Base

A subsystem separate from per-case retrieval: admins can upload reference material (protocols, formularies, internal guidelines — whatever) via `/rag-docs`, which gets embedded with MedCPT into the shared `medical_docs` collection that every analysis tool can draw on regardless of which patient case it's running for. Uploading, listing, deleting, and reindexing are all gated behind `require_admin`. On startup, if that collection is empty but files already exist on disk, it self-indexes without anyone needing to click "reindex" — useful for seeding a fresh deployment with a pre-populated reference set. There's a matching frontend page at `RagDocsPage.tsx`.

---

## API Surface

**Auth** — `POST /auth/request-otp`, `/auth/register`, `/auth/verify-otp`, `/auth/logout`

**Users** — `GET /users/me`, `GET /users/roles`, `GET/PATCH/DELETE /users[/{id}]` (last three admin-only)

**Notebooks** — `GET/POST /notebooks`, `GET/DELETE /notebooks/{id}`, `POST /notebooks/{id}/sources`

**Analysis** (each is a `POST .../{tool}` to run + `GET .../{tool}` to fetch the last result), all under `/notebooks/{id}/`:
`analyze` (differential diagnosis) · `interactions` · `icd11` · `literature` · `risk` · `rare-diseases` · `contradictions` · `guidelines` · `draft` — plus `chat` (GET loads history, POST streams a response via SSE) and `chat/history` (persist).

All analysis endpoints require the case to already have synthesized `documentation` — i.e., at least one source uploaded.

**RAG Docs** (admin-only) — `GET/POST /rag-docs`, `DELETE /rag-docs/{filename}`, `POST /rag-docs/reindex`

**Misc** — `GET /health`

---

## Frontend

`App.tsx` gates everything on session state: loading → spinner, no user → `AuthPage` replaces the whole app, logged in → normal routes. `/users` and `/rag-docs` only register when `role_id === 3`.

A case lives on `NotebookPage.tsx` as three panels: **Sources** (upload/manage documents — uploads stream progress back via SSE while the backend ingests, embeds, and re-synthesizes the case documentation), **Chat** (freeform Q&A over the case, tokens streamed in and appended live), and **Tools** (one modal per analysis service from the table above, each independently runnable and re-runnable). Vite's dev server proxies `/api/*` straight to the backend container, so the frontend just calls relative `/api/...` paths throughout.

---

## Extending It

**New role**: add to `Role(IntEnum)` and `ROLE_DEFINITIONS` in `backend/models/roles.py`, seed it in `db/postgres.py:init_schema()`, mirror it in `frontend/src/types.ts`'s `ROLES` map, add a badge color in `index.scss`.

**New analysis tool**: define its output shape as a Pydantic model in `data_model.py`; write a service that pulls from `NotebookRAG` (and any real external source that applies) and calls `ollama.chat(..., format=Model.model_json_schema())`; add `POST`/`GET` handlers in `routers/notebooks.py` following the existing load→guard→run→persist pattern; mirror the type in `types.ts`; copy an existing modal (e.g. `RiskAnalysisModal.tsx`) as a template; wire a button into `ToolsPanel.tsx` and state into `NotebookPage.tsx`.

---

## Known Constraints

- **No horizontal scaling** — ChromaDB is embedded on disk and the Postgres pool is per-process; scaling out would need a real vector DB server and pgBouncer.
- **Ollama is host-only, not containerized** — GPU strongly recommended; CPU inference is slow enough to be a real UX problem.
- **NER effectively requires a GPU** — without one it fails gracefully and keyword extraction (which several tools depend on) is disabled.
- **No OTP rate limiting** — nothing stops repeated OTP requests; needs addressing before any public exposure.
- **Logout doesn't invalidate the session server-side** — only the cookie is cleared, the session row survives until its 30-day expiry.
- **No analysis history** — every tool run overwrites the previous result for that case; there's no audit trail.

This reads, overall, like a self-hosted tool built for one clinic/team on one machine rather than a multi-tenant SaaS product — the infrastructure choices (host GPU, on-disk vector stores, no rate limiting, no session revocation) all point the same direction.
