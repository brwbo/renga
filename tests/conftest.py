import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RENGA_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("RENGA_FRAMES", str(tmp_path / "frames"))
    monkeypatch.setenv("RENGA_FILES", str(tmp_path / "files"))
    for name in [m for m in sys.modules if m.startswith("renga")]:
        del sys.modules[name]
    main = importlib.import_module("renga.main")
    with TestClient(main.app) as c:
        yield c
