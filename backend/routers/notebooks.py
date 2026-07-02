import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from db.mongo import get_db
from db.postgres import get_conn
from services.ingestion import extract_file, extract_url, validate_upload
from services.generation import generate_notebook_content
from services.clinical_analyzer import ClinicalAnalyzer
from services.interaction_checker import InteractionChecker
from services.icd11_tree import ICD11TreeService
from services.literature_review import LiteratureReviewService
from services.notebook_rag import NotebookRAG

router = APIRouter(prefix="/notebooks")


# ── SSE streaming helper ──────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def _stream_tool(task_fn: Callable):
    """
    Runs `task_fn(on_progress)` in a daemon thread, yielding SSE events.
    `task_fn` receives a single arg: on_progress(step: str, pct: int).
    Yields progress events during execution, then a result or error event.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    result_holder: dict = {}

    def on_progress(step: str, pct: int) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            _sse({"type": "progress", "step": step, "progress": pct}),
        )

    def run() -> None:
        try:
            result_holder["data"] = task_fn(on_progress)
        except Exception as exc:
            result_holder["error"] = str(exc)
        loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    threading.Thread(target=run, daemon=True).start()

    while True:
        msg = await queue.get()
        if msg is None:
            break
        yield msg

    if "error" in result_holder:
        yield _sse({"type": "error", "message": result_holder["error"]})
    else:
        yield _sse({"type": "result", "data": result_holder["data"]})


def _user_id(request: Request) -> str:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return ""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id FROM sessions s
                JOIN users u ON u.user_id = s.user_id
                WHERE s.session_id = %s AND s.expires_at > NOW()
                """,
                (session_id,),
            )
            row = cur.fetchone()
    return str(row[0]) if row else ""


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


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{notebook_id}")
def delete_notebook(notebook_id: str, request: Request):
    uid = _user_id(request)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM notebooks WHERE notebook_id = %s AND user_id = %s",
                (notebook_id, uid),
            )
            if cur.rowcount == 0:
                return JSONResponse(status_code=404, content={"error": "Not found"})
        conn.commit()

    get_db().notebook_content.delete_one({"notebook_id": notebook_id})
    NotebookRAG.delete_notebook(notebook_id)

    return {"ok": True}


# ── Add sources ───────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/sources")
async def add_sources(
    notebook_id: str,
    request: Request,
    files: list[UploadFile] = File(default=[]),
    urls: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    anonymize: str = Form(default="false"),
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

    should_anonymize = anonymize.lower() == "true"

    # Read file bytes eagerly before entering the thread
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        if f.filename:
            file_data.append((f.filename, await f.read()))

    url_list = [u.strip() for u in (urls or "").split() if u.strip()]
    text_content = text.strip() if text and text.strip() else None

    n_sources = len(file_data) + len(url_list) + (1 if text_content else 0)

    def task(on_progress: Callable) -> dict:
        def _process(content: str) -> str:
            if not should_anonymize:
                return content
            from services.anonymizer import anonymize as _anonymize
            return _anonymize(content)

        new_sources: list[dict] = []
        pct_per_source = 65 // max(n_sources, 1)
        current_pct = 0

        for filename, file_bytes in file_data:
            try:
                safe_name, file_type = validate_upload(filename, file_bytes)
            except ValueError as exc:
                raise exc
            on_progress(f"Extracting text from {safe_name}…", current_pct)
            content = extract_file(file_bytes, file_type)
            if should_anonymize:
                on_progress(f"Anonymizing {safe_name}…", current_pct + pct_per_source // 2)
            content = _process(content)
            new_sources.append({
                "id": str(uuid.uuid4()),
                "type": file_type,
                "name": safe_name,
                "content": content,
            })
            current_pct = min(65, current_pct + pct_per_source)

        for url in url_list:
            on_progress(f"Fetching {url}…", current_pct)
            content = extract_url(url)
            if should_anonymize:
                on_progress("Anonymizing…", current_pct + pct_per_source // 2)
            content = _process(content)
            new_sources.append({
                "id": str(uuid.uuid4()),
                "type": "url",
                "name": url,
                "content": content,
            })
            current_pct = min(65, current_pct + pct_per_source)

        if text_content:
            on_progress("Processing text…", current_pct)
            content = _process(text_content)
            name = (content[:60] + "…") if len(content) > 60 else content
            new_sources.append({
                "id": str(uuid.uuid4()),
                "type": "text",
                "name": name,
                "content": content,
            })

        if not new_sources:
            raise ValueError("No valid sources provided")

        db = get_db()
        existing_doc = db.notebook_content.find_one({"notebook_id": notebook_id}) or {}
        all_sources = existing_doc.get("sources", []) + new_sources

        on_progress("Generating notebook summary…", 70)
        generated = generate_notebook_content(all_sources)
        title = generated["title"]
        documentation = generated["documentation"]
        summary = generated["summary"]

        on_progress("Saving…", 90)
        now = _now()

        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {
                "sources": all_sources,
                "documentation": documentation,
                "summary": summary,
                "updated_at": now,
            }},
            upsert=True,
        )

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

        for s in new_sources:
            threading.Thread(
                target=NotebookRAG.index_source,
                args=(notebook_id, s["id"], s["name"], s["content"]),
                daemon=True,
            ).start()

        return {
            "sources": [{"id": s["id"], "type": s["type"], "name": s["name"]} for s in new_sources],
            "title": title,
            "documentation": documentation,
            "summary": summary,
        }

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ── Clinical analysis ─────────────────────────────────────────────────────────

@router.post("/{notebook_id}/analyze")
async def analyze_notebook(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    documentation = doc.get("documentation") or ""
    if not documentation:
        return JSONResponse(status_code=400, content={"error": "No documentation generated yet. Add sources first."})

    analyzer = ClinicalAnalyzer()
    db = get_db()

    def task(on_progress):
        result = analyzer.analyze(uid, notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"clinical_analysis": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/analysis")
def get_analysis(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "clinical_analysis" not in doc:
        return JSONResponse(status_code=404, content={"error": "No analysis yet"})
    return doc["clinical_analysis"]


# ── Drug interaction checker ──────────────────────────────────────────────────

@router.post("/{notebook_id}/interactions")
async def check_interactions(notebook_id: str, request: Request):
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
    db = get_db()

    def task(on_progress):
        result = checker.interaction_check(documentation, notebook_id, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"drug_interactions": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/interactions")
def get_interactions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "drug_interactions" not in doc:
        return JSONResponse(status_code=404, content={"error": "No drug interaction analysis yet"})
    return doc["drug_interactions"]


# ── ICD-11 tree ───────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/icd11")
async def run_icd11(notebook_id: str, request: Request):
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
    db = get_db()

    def task(on_progress):
        result = service.generate_icd11_tree(documentation, notebook_id, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"icd11": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/icd11")
def get_icd11(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "icd11" not in doc:
        return JSONResponse(status_code=404, content={"error": "No ICD-11 analysis yet"})
    return doc["icd11"]


# ── Literature review ─────────────────────────────────────────────────────────

@router.post("/{notebook_id}/literature")
async def run_literature(notebook_id: str, request: Request):
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
    db = get_db()

    def task(on_progress):
        result = service.analyze(uid, notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"literature": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/literature")
def get_literature(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "literature" not in doc:
        return JSONResponse(status_code=404, content={"error": "No literature review yet"})
    return doc["literature"]


# ── Risk analysis ─────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/risk")
async def run_risk(notebook_id: str, request: Request):
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
    analyzer = RiskAnalyzer()
    db = get_db()

    def task(on_progress):
        result = analyzer.analyze(notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"risk": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/risk")
def get_risk(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "risk" not in doc:
        return JSONResponse(status_code=404, content={"error": "No risk analysis yet"})
    return doc["risk"]


# ── Rare disease finder ───────────────────────────────────────────────────────

@router.post("/{notebook_id}/rare-diseases")
async def run_rare_diseases(notebook_id: str, request: Request):
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
    service = RareDiseaseService()
    db = get_db()

    def task(on_progress):
        result = service.analyze(notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"rare_diseases": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/rare-diseases")
def get_rare_diseases(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "rare_diseases" not in doc:
        return JSONResponse(status_code=404, content={"error": "No rare disease analysis yet"})
    return doc["rare_diseases"]


# ── Contradiction detector ────────────────────────────────────────────────────

@router.post("/{notebook_id}/contradictions")
async def run_contradictions(notebook_id: str, request: Request):
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
    detector = ContradictionDetector()
    db = get_db()

    def task(on_progress):
        result = detector.analyze(notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"contradictions": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{notebook_id}/contradictions")
def get_contradictions(notebook_id: str, request: Request):
    uid = _user_id(request)
    doc = get_db().notebook_content.find_one({"notebook_id": notebook_id, "user_id": uid})
    if not doc or "contradictions" not in doc:
        return JSONResponse(status_code=404, content={"error": "No contradiction analysis yet"})
    return doc["contradictions"]


# ── Guidelines conformance ────────────────────────────────────────────────────

@router.post("/{notebook_id}/guidelines")
async def run_guidelines(notebook_id: str, request: Request):
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
    service = GuidelinesConformance()
    db = get_db()

    def task(on_progress):
        result = service.analyze(notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"guidelines": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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
async def run_draft(notebook_id: str, request: Request):
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
    drafter = DocumentDrafter()
    db = get_db()

    def task(on_progress):
        result = drafter.draft_all(notebook_id, documentation, on_progress=on_progress)
        db.notebook_content.update_one(
            {"notebook_id": notebook_id},
            {"$set": {"drafts": result, "updated_at": _now()}},
        )
        return result

    return StreamingResponse(
        _stream_tool(task),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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
