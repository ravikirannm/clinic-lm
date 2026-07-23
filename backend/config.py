import os
from dotenv import load_dotenv

load_dotenv()

POSTGRES_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')} "
    f"dbname={os.getenv('POSTGRES_DB', 'clinic_db')} "
    f"user={os.getenv('POSTGRES_USER', 'clinic_user')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'clinic_pass')}"
)

MONGODB_URI = os.getenv(
    'MONGODB_URI',
    'mongodb://clinic_user:clinic_pass@mongodb:27017/clinic_db?authSource=admin'
)

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://host.docker.internal:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')

def _resolve_device() -> str:
    """Return 'cpu' if TORCH_DEVICE=cpu, otherwise auto-detect CUDA."""
    if os.getenv("TORCH_DEVICE", "").lower() == "cpu":
        return "cpu"
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

TORCH_DEVICE: str = _resolve_device()

BIO_EMAIL = os.getenv("BIO_EMAIL", "")

ICD11_CLIENT_ID = os.getenv("ICD11_CLIENT_ID", "")
ICD11_CLIENT_SECRET = os.getenv("ICD11_CLIENT_SECRET", "")

GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD", "")

RAG_DOCS_DIR = os.getenv("RAG_DOCS_DIR", "./rag_docs")


