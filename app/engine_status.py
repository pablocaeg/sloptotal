"""Track engine loading state for health monitoring."""

import threading

_lock = threading.Lock()
_status: dict[str, dict[str, str | None]] = {}


def mark_loaded(engine_key: str) -> None:
    """Record that an engine has loaded successfully."""
    with _lock:
        _status[engine_key] = {
            "state": "loaded",
            "error": None,
        }


def mark_failed(engine_key: str, error: Exception | str) -> None:
    """Record that an engine failed to load."""
    with _lock:
        _status[engine_key] = {
            "state": "failed",
            "error": str(error),
        }


def get_status() -> dict[str, dict[str, str | None]]:
    """Return a snapshot of all recorded engine states."""
    with _lock:
        return {key: state.copy() for key, state in _status.items()}


def get_health_summary() -> dict:
    """Return loaded and failed engine information for /health."""
    with _lock:
        loaded = sum(1 for state in _status.values() if state["state"] == "loaded")
        failed = [key for key, state in _status.items() if state["state"] == "failed"]

    return {
        "loaded": loaded,
        "failed": failed,
    }


def reset_status() -> None:
    """Clear all recorded engine states."""
    with _lock:
        _status.clear()
