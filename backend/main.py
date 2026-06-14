from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.postgres import init_pool, init_schema
from routers import notebooks, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    init_schema()
    yield


app = FastAPI(title="Clinic LM API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(notebooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
