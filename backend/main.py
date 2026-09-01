from fastapi import FastAPI
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
