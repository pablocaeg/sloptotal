import importlib
import threading
import types

import pytest

from app import main
from app.analyzer import get_engine_list
from app.engine_status import get_health_summary, get_status, reset_status


class _InlineThread:
    def __init__(self, target, daemon=False):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def preload(monkeypatch):
    """Run the real preload loop synchronously, with model loaders stubbed out."""
    real_import = importlib.import_module

    def run(failing: str | None = None):
        def fake_import(name, *args, **kwargs):
            if not name.startswith("app.engines."):
                return real_import(name, *args, **kwargs)

            def loader():
                if name.endswith(f".{failing}"):
                    raise RuntimeError("download failed")

            return types.SimpleNamespace(
                _load_model=loader, _init_pool=loader, _load_distil_model=loader
            )

        reset_status()
        monkeypatch.setattr(importlib, "import_module", fake_import)
        monkeypatch.setattr(threading, "Thread", _InlineThread)
        main._preload_models()
        monkeypatch.undo()
        return get_status()

    return run


def test_preload_marks_every_preloaded_engine_by_its_real_key(preload):
    status = preload()
    engine_keys = {key for key, _, _ in get_engine_list()}

    assert len(status) == 11
    assert set(status) <= engine_keys
    assert all(state["state"] == "loaded" for state in status.values())


def test_a_failing_loader_is_reported_and_does_not_stop_the_others(preload):
    status = preload(failing="classifier_superannotate")

    assert status["classifier_superannotate"] == {
        "state": "failed",
        "error": "download failed",
    }
    assert get_health_summary() == {
        "loaded": 10,
        "failed": ["classifier_superannotate"],
    }


def test_ready_log_ends_with_one_star_line(preload, caplog):
    caplog.set_level("INFO", logger="sloptotal")
    preload()
    messages = [r.getMessage() for r in caplog.records if r.name == "sloptotal"]

    assert messages[-1] == main.STAR_LINE
    assert messages.count(main.STAR_LINE) == 1
    assert "engines ready" in messages[-2]


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_sloptotal_quiet_drops_the_star_line(preload, caplog, monkeypatch, value):
    monkeypatch.setenv("SLOPTOTAL_QUIET", value)
    caplog.set_level("INFO", logger="sloptotal")
    preload()

    assert main.STAR_LINE not in [r.getMessage() for r in caplog.records]
