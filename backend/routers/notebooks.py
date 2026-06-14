import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from db.mongo import get_db
from db.postgres import get_conn
from services.ingestion import extract_pdf, extract_url
from services.generation import generate_notebook_content
from services.clinical_analyzer import ClinicalAnalyzer
from services.interaction_checker import InteractionChecker
from services.icd11_tree import ICD11TreeService
from services.literature_review import LiteratureReviewService
from services.notebook_rag import NotebookRAG

router = APIRouter(prefix="/notebooks")


def _user_id(request: Request) -> str:
    return request.cookies.get("user_id", "")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
def list_notebooks(request: Request):
    uid = _user_id(request)
    if not uid:
        return []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT notebook_id, title, source_titles, updated_at
                FROM notebooks
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (uid,),
            )
            rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "title": r[1],
            "sourceCount": len(r[2]) if r[2] else 0,
            "updatedAt": r[3].strftime("%-d %b") if r[3] else "",
        }
        for r in rows
    ]


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("")
def create_notebook(request: Request):
    uid = _user_id(request)
    if not uid:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    notebook_id = str(uuid.uuid4())
    now = _now()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notebooks (notebook_id, user_id, title, source_titles, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (notebook_id, uid, "Untitled notebook", [], now),
            )
        conn.commit()

    get_db().notebook_content.insert_one(
        {
            "notebook_id": notebook_id,
            "user_id": uid,
            "sources": [],
            "documentation": None,
            "summary": None,
            "updated_at": now,
        }
    )

    return {"notebook_id": notebook_id}


# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/{notebook_id}")
def get_notebook(notebook_id: str, request: Request):
    uid = _user_id(request)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT notebook_id, title, updated_at
                FROM notebooks
                WHERE notebook_id = %s AND user_id = %s
                """,
                (notebook_id, uid),
            )
            row = cur.fetchone()

    if not row:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id}) or {}

    sources = [
        {"id": s["id"], "type": s["type"], "name": s["name"]}
        for s in doc.get("sources", [])
    ]

    return {
        "id": str(row[0]),
        "title": row[1],
        "updatedAt": row[2].strftime("%-d %b") if row[2] else "",
        "sources": sources,
        "documentation": doc.get("documentation"),
        "summary": doc.get("summary"),
    }


# ── Add source ────────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/sources")
async def add_source(
    notebook_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    source_type: str = Form(...),
    url: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    uid = _user_id(request)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT notebook_id FROM notebooks WHERE notebook_id = %s AND user_id = %s",
                (notebook_id, uid),
            )
            if not cur.fetchone():
                return JSONResponse(status_code=404, content={"error": "Not found"})

    # Extract content
    source_id = str(uuid.uuid4())
    content = ""
    name = ""

    if source_type == "pdf" and file:
        file_bytes = await file.read()
        content = extract_pdf(file_bytes)
        name = file.filename or "document.pdf"
    elif source_type == "url" and url:
        content = extract_url(url.strip())
        name = url.strip()
    elif source_type == "text" and text:
        content = text.strip()
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid source data"})

    # De-identify PII/PHI before saving or indexing anything
    from services.anonymizer import anonymize
    content = anonymize(content)

    # Derive text-source name after anonymization so the label is also de-identified
    if source_type == "text":
        name = (content[:60] + "…") if len(content) > 60 else content

    # Merge with existing sources
    db = get_db()
    existing_doc = db.notebook_content.find_one({"notebook_id": notebook_id}) or {}
    existing_sources: list = existing_doc.get("sources", [])
    new_source = {"id": source_id, "type": source_type, "name": name, "content": content}
    all_sources = existing_sources + [new_source]

    # Generate documentation via Ollama
    generated = generate_notebook_content(all_sources)
    title = generated["title"]
    documentation = generated["documentation"]
    summary = generated["summary"]

    now = _now()

    # Persist to MongoDB
    db.notebook_content.update_one(
        {"notebook_id": notebook_id},
        {
            "$set": {
                "sources": all_sources,
                "documentation": documentation,
                "summary": summary,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    # Update PostgreSQL metadata
    source_titles = [s["name"] for s in all_sources]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notebooks
                SET title = %s, source_titles = %s, updated_at = %s
                WHERE notebook_id = %s
                """,
                (title, source_titles, now, notebook_id),
            )
        conn.commit()

    # Index source content into the per-notebook vector store (runs after response)
    background_tasks.add_task(NotebookRAG.index_source, notebook_id, source_id, name, content)

    return {
        "source_id": source_id,
        "name": name,
        "type": source_type,
        "title": title,
        "documentation": documentation,
        "summary": summary,
    }


# ── Clinical analysis ─────────────────────────────────────────────────────────

@router.post("/{notebook_id}/analyze")
def analyze_notebook(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(status_code=400, content={"error": "No documentation generated yet. Add sources first."})

    analyzer = ClinicalAnalyzer()
    result = analyzer.analyze(uid, notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"clinical_analysis": result, "updated_at": _now()}},
    )

    return result


@router.get("/{notebook_id}/analysis")
def get_analysis(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "clinical_analysis" not in doc:
        return JSONResponse(status_code=404, content={"error": "No analysis yet"})
    return doc["clinical_analysis"]


# ── Drug interaction checker ──────────────────────────────────────────────────

@router.post("/{notebook_id}/interactions")
def check_interactions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."}
        )

    checker = InteractionChecker()
    result = checker.interaction_check(documentation, notebook_id)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"drug_interactions": result, "updated_at": _now()}},
    )

    return result


@router.get("/{notebook_id}/interactions")
def get_interactions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "drug_interactions" not in doc:
        return JSONResponse(status_code=404, content={"error": "No drug interaction analysis yet"})
    return doc["drug_interactions"]


# ── ICD-11 tree ───────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/icd11")
def run_icd11(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    service = ICD11TreeService()
    result = service.generate_icd11_tree(documentation, notebook_id)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"icd11": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/icd11")
def get_icd11(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "icd11" not in doc:
        return JSONResponse(status_code=404, content={"error": "No ICD-11 analysis yet"})
    return doc["icd11"]


# ── Literature review ─────────────────────────────────────────────────────────

@router.post("/{notebook_id}/literature")
def run_literature(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    service = LiteratureReviewService()
    result = service.analyze(uid, notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"literature": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/literature")
def get_literature(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "literature" not in doc:
        return JSONResponse(status_code=404, content={"error": "No literature review yet"})
    return doc["literature"]


# ── Risk analysis ─────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/risk")
def run_risk(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    from services.risk_analyser import RiskAnalyzer
    result = RiskAnalyzer().analyze(notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"risk": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/risk")
def get_risk(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "risk" not in doc:
        return JSONResponse(status_code=404, content={"error": "No risk analysis yet"})
    return doc["risk"]


# ── Rare disease finder ───────────────────────────────────────────────────────

@router.post("/{notebook_id}/rare-diseases")
def run_rare_diseases(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    from services.rare_disease import RareDiseaseService
    result = RareDiseaseService().analyze(notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"rare_diseases": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/rare-diseases")
def get_rare_diseases(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "rare_diseases" not in doc:
        return JSONResponse(status_code=404, content={"error": "No rare disease analysis yet"})
    return doc["rare_diseases"]


# ── Contradiction detector ────────────────────────────────────────────────────

@router.post("/{notebook_id}/contradictions")
def run_contradictions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    from services.contradiction_detector import ContradictionDetector
    result = ContradictionDetector().analyze(notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"contradictions": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/contradictions")
def get_contradictions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "contradictions" not in doc:
        return JSONResponse(status_code=404, content={"error": "No contradiction analysis yet"})
    return doc["contradictions"]


# ── Guidelines conformance ────────────────────────────────────────────────────

@router.post("/{notebook_id}/guidelines")
def run_guidelines(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    from services.guidelines_conformance import GuidelinesConformance
    result = GuidelinesConformance().analyze(notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"guidelines": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/guidelines")
def get_guidelines(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "guidelines" not in doc:
        return JSONResponse(status_code=404, content={"error": "No guidelines analysis yet"})
    return doc["guidelines"]


# ── Chat ──────────────────────────────────────────────────────────────────────

from services.data_model import ChatRequest, SaveHistoryBody


# ── Document drafter ──────────────────────────────────────────────────────────

@router.post("/{notebook_id}/draft")
def run_draft(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(
            status_code=400,
            content={"error": "No documentation generated yet. Add sources first."},
        )

    from services.document_drafter import DocumentDrafter
    result = DocumentDrafter().draft_all(notebook_id, documentation)

    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"drafts": result, "updated_at": _now()}},
    )
    return result


@router.get("/{notebook_id}/draft")
def get_draft(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "drafts" not in doc:
        return JSONResponse(status_code=404, content={"error": "No drafts yet"})
    return doc["drafts"]


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.get("/{notebook_id}/chat")
def get_chat_history(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"messages": doc.get("chat_history", [])}


@router.post("/{notebook_id}/chat/history")
def save_chat_history(notebook_id: str, body: SaveHistoryBody, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    get_db().notebook_content.update_one(
        {"notebook_id": notebook_id},
        {"$set": {"chat_history": body.messages, "updated_at": _now()}},
    )
    return {"ok": True}


@router.post("/{notebook_id}/chat")
def chat(notebook_id: str, body: ChatRequest, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""

    from services.chat_bot import ChatBot
    bot = ChatBot()

    return StreamingResponse(
        bot.stream(notebook_id, documentation, body.messages, body.query),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
