import pytest
from app.autoconfig import choose_profile, compute_config


@pytest.mark.parametrize(
    ("hw", "expected"),
    [
        ({"cuda_available": True, "gpu_vram_gb": 4.0}, "performance"),
        ({"cuda_available": False, "gpu_vram_gb": 0.0, "ram_gb": 16.0}, "performance"),
        ({"cuda_available": False, "gpu_vram_gb": 0.0, "ram_gb": 8.0}, "standard"),
        ({"cuda_available": False, "gpu_vram_gb": 0.0, "ram_gb": 7.9}, "lite"),
    ],
)
def test_choose_profile_from_hardware(hw, expected, monkeypatch):
    monkeypatch.delenv("SLOPTOTAL_PROFILE", raising=False)
    assert choose_profile(hw) == expected


@pytest.mark.parametrize("profile", ["lite", "standard", "performance"])
def test_choose_profile_explicit_override(profile, monkeypatch):
    monkeypatch.setenv("SLOPTOTAL_PROFILE", profile)
    hw = {"cuda_available": False, "gpu_vram_gb": 0.0, "ram_gb": 4.0}
    assert choose_profile(hw) == profile


def test_choose_profile_ignores_invalid_override(monkeypatch):
    monkeypatch.setenv("SLOPTOTAL_PROFILE", "unknown")
    hw = {"cuda_available": False, "gpu_vram_gb": 0.0, "ram_gb": 8.0}
    assert choose_profile(hw) == "standard"


@pytest.mark.parametrize(
    ("hw", "profile", "expected_snippet_workers", "expected_full_workers"),
    [
        (
            {"cpu_count": 2, "ram_gb": 4, "cuda_available": False, "gpu_vram_gb": 0},
            "lite",
            2,
            2,
        ),
        (
            {"cpu_count": 4, "ram_gb": 8, "cuda_available": False, "gpu_vram_gb": 0},
            "standard",
            2,
            2,
        ),
        (
            {"cpu_count": 16, "ram_gb": 64, "cuda_available": False, "gpu_vram_gb": 0},
            "performance",
            4,
            14,
        ),
        (
            {"cpu_count": 8, "ram_gb": 16, "cuda_available": True, "gpu_vram_gb": 8},
            "performance",
            4,
            8,
        ),
    ],
)
def test_compute_config_worker_counts(
    hw, profile, expected_snippet_workers, expected_full_workers
):
    config = compute_config(hw, profile)
    snippet_workers = int(config["SLOPTOTAL_SNIPPET_WORKERS"])
    full_workers = int(config["SLOPTOTAL_FULL_WORKERS"])
    assert snippet_workers > 0
    assert full_workers > 0
