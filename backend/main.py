from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routes import ai, auth, datasets, reconciliation

app = FastAPI(title="Reconcile API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(reconciliation.router)
app.include_router(ai.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Vercel Services routes a request to a service with its full original path
# intact (e.g. a rewrite matching "/api/backend/*" reaches this app as
# "/api/backend/auth/login", not "/auth/login" -- see vercel.json and
# README's "Deploying to Vercel" section). Rather than force local
# development and tests to always use that prefix, every route above is
# additionally mounted under /api/backend so the exact same app works
# unprefixed locally and prefixed behind Vercel's rewrite.
_vercel_prefix = APIRouter(prefix="/api/backend")
_vercel_prefix.include_router(auth.router)
_vercel_prefix.include_router(datasets.router)
_vercel_prefix.include_router(reconciliation.router)
_vercel_prefix.include_router(ai.router)


@_vercel_prefix.get("/health")
def health_prefixed():
    return {"status": "ok"}


app.include_router(_vercel_prefix)
