from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import services
from .api import router
from .config import get_settings
from .db import SessionLocal
from .models import Account
from .security_layer import _keys, limiter

log = logging.getLogger("cloudgini")


def seed() -> None:
    s = get_settings()
    with SessionLocal() as db:
        if s.seed_simulated and db.get(Account, "sim-demo") is None:
            db.add(Account(id="sim-demo", provider="simulated", name="Simulated demo estate", scope_id="demo-shop",
                           data_source="simulated", remediation_enabled=False))
        for project in filter(None, (x.strip() for x in s.gcp_projects.split(","))):
            if db.get(Account, f"gcp-{project}") is None:
                db.add(Account(id=f"gcp-{project}", provider="gcp", name=f"GCP {project}", scope_id=project,
                               data_source="real", remediation_enabled=False))
        db.commit()
        sim = db.get(Account, "sim-demo")
        if sim and sim.last_scan_at is None:
            services.scan_account(db, sim)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _keys():
        log.warning("CLOUDGINI_API_KEYS is empty: every API call will be refused. Run scripts/init-env.sh.")
    seed()
    yield


app = FastAPI(
    title="CloudGini API",
    version="0.1.0",
    description="Cloud cost optimisation, unused-resource cleanup and security checks. Prototype. "
                "Every figure is labelled real or simulated, and savings as estimated or verified.",
    lifespan=lifespan,
    dependencies=[Depends(limiter.check)],
)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_methods=["GET", "POST", "PUT", "PATCH"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
