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

BIO_EMAIL = os.getenv("BIO_EMAIL", "")

ICD11_CLIENT_ID = os.getenv("ICD11_CLIENT_ID", "")
ICD11_CLIENT_SECRET = os.getenv("ICD11_CLIENT_SECRET", "")