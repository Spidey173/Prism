from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.documents import router as documents_router
from app.routers.health import router as health_router
from app.routers.issues import router as issues_router
from app.services.document_service import mark_interrupted_runs_failed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    mark_interrupted_runs_failed()
    yield


app = FastAPI(title="Prism API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(issues_router)
