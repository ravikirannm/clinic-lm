from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from dependencies import require_admin
from services import rag_docs

router = APIRouter(prefix="/rag-docs")


@router.get("")
def list_docs(admin: dict = Depends(require_admin)):
    return rag_docs.list_docs()


@router.post("")
async def upload_docs(
    files: list[UploadFile] = File(...),
    admin: dict = Depends(require_admin),
):
    saved = []
    errors = []
    for f in files:
        file_bytes = await f.read()
        try:
            saved.append(rag_docs.save_doc(f.filename or "", file_bytes))
        except ValueError as exc:
            errors.append({"file": f.filename, "error": str(exc)})
    return {"saved": saved, "errors": errors}


@router.delete("/{filename}")
def delete_doc(filename: str, admin: dict = Depends(require_admin)):
    if not rag_docs.delete_doc(filename):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"ok": True}


@router.post("/reindex")
def reindex(admin: dict = Depends(require_admin)):
    try:
        return rag_docs.rebuild_index()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
