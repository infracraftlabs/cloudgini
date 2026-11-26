import hashlib
import os
import tempfile

import pytest

KEYS = {"viewer": "test-viewer-key", "analyst": "test-analyst-key", "operator": "test-operator-key", "admin": "test-admin-key"}
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["CLOUDGINI_DATABASE_URL"] = os.environ.get("CLOUDGINI_TEST_DATABASE_URL", f"sqlite:///{_db}")
os.environ["CLOUDGINI_API_KEYS"] = ",".join(f"{r}-user:{r}:{hashlib.sha256(k.encode()).hexdigest()}" for r, k in KEYS.items())
os.environ["CLOUDGINI_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["CLOUDGINI_SENSITIVE_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import registry  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    registry.reset_cache()
    with TestClient(app) as c:
        yield c


def auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {KEYS[role]}"}
