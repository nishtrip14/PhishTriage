import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


@pytest.fixture
def no_network(monkeypatch):
    """Fail the test if anything tries to open a network connection."""
    def blocked(*args, **kwargs):
        raise AssertionError(f"network access attempted: {args[:1]}")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture(scope="session")
def toy_artifact(tmp_path_factory):
    """A tiny synthetic classifier artifact for workflow tests (not an accuracy model)."""
    import numpy as np
    from phishtriage import inference as I, models as M
    phish = ["verify your account password now or it will be suspended", "urgent confirm billing details today"] * 5
    legit = ["minutes from the weekly team meeting", "lunch on friday let me know"] * 5
    frozen = {"model_id": "tfidf_logreg__artifact_normalized", "kind": "tfidf_logreg",
              "variant": "artifact_normalized", "params": {"C": 1.0}, "threshold": 0.5,
              "threshold_rule": "synthetic", "selection_metric": "synthetic"}
    pipe = M.build_pipeline("tfidf_logreg", "artifact_normalized", frozen["params"])
    pipe.fit(phish + legit, np.array([1] * 10 + [0] * 10))
    path = I.save_artifact(pipe, frozen, tmp_path_factory.mktemp("toy"), dataset={}, results={}, environment="test")
    return I.load_artifact(path)


@pytest.fixture
def demo_tools(toy_artifact):
    from phishtriage import agent_replays as AR, retrieval as R, tools as T
    from phishtriage.evidence import CaseStore
    store = CaseStore()
    for name in AR.DEMO_CASES:
        store.add(AR.build_demo_case(name, f"case-{name}"))
    return T.TriageTools(store, model=toy_artifact[0], manifest=toy_artifact[1], index=R.PlaybookIndex())
