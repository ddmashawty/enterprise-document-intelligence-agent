from __future__ import annotations

from pathlib import Path

import pytest

from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.seed import seed_kaoyan

KAOYAN_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kaoyan"


@pytest.fixture(scope="session")
def kaoyan_store(tmp_path_factory: pytest.TempPathFactory) -> KaoyanStore:
    """Temp kaoyan.db seeded from the committed bundle (majors.csv / sources.json); no network."""
    if not (KAOYAN_DATA_DIR / "sources.json").exists():
        pytest.skip("data/kaoyan bundle not present")
    store = KaoyanStore(tmp_path_factory.mktemp("kaoyan_k5") / "kaoyan.db")
    seed_kaoyan(store, KAOYAN_DATA_DIR)
    return store
