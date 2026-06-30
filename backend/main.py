import logging
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.postgres import init_pool, init_schema
from db.mongo import init_indexes
from routers import notebooks, users
from routers import auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
    force=True,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    init_schema()
    init_indexes()
    _preload_models()
    yield


def _preload_models():
    """Eagerly load GPU models so the first request doesn't pay the cold-start penalty."""
    import torch

    if torch.cuda.is_available():
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        logger.info("GPU detected: %s — %.1f GB VRAM", torch.cuda.get_device_name(0), vram_total)
    else:
        logger.info("No GPU detected — models will run on CPU")

    try:
        from services.extract_keywords import ExtractKeywords
        ExtractKeywords()  # singleton-style: clinical_analyzer reuses the module-level instance
        logger.info("NER model preloaded")
    except Exception as exc:
        logger.warning("NER model preload failed (will retry on first request): %s", exc)

    try:
        from services.notebook_rag import NotebookRAG
        NotebookRAG._ensure_loaded()
        logger.info("NotebookRAG embedding model preloaded")
    except Exception as exc:
        logger.warning("NotebookRAG preload failed: %s", exc)


app = FastAPI(title="Clinic LM API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(notebooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
