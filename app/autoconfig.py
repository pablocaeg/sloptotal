"""
Hardware auto-detection and optimal configuration for SlopTotal.

Self-hosted users run one command; this module detects CPU, RAM, GPU
and configures the server optimally. Explicit env vars always override.

Profiles:
  lite        — <8GB RAM, no GPU. 4 fast engines only. Minimal footprint.
  standard    — 8-16GB RAM or CPU-only. All 21 engines, no replicas.
  performance — 16GB+ RAM or GPU. All engines, pool replicas or CUDA.
"""

import logging
import os

log = logging.getLogger("sloptotal.autoconfig")


def detect_hardware() -> dict:
    """Detect available hardware. Pure detection, no side effects."""
    import torch

    cpu_count = os.cpu_count() or 4
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        # Fallback: read /proc/meminfo on Linux
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        ram_gb = round(int(line.split()[1]) / (1024**2), 1)
                        break
                else:
                    ram_gb = 8.0  # safe guess
        except Exception:
            ram_gb = 8.0

    gpu_name = None
    gpu_vram_gb = 0.0
    cuda_available = torch.cuda.is_available()
    if cuda_available:
        try:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_vram_gb = round(
                torch.cuda.get_device_properties(0).total_mem / (1024**3), 1
            )
        except Exception:
            pass

    return {
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram_gb,
    }


def choose_profile(hw: dict) -> str:
    """Choose a configuration profile based on hardware."""
    # Explicit override
    explicit = os.getenv("SLOPTOTAL_PROFILE")
    if explicit and explicit in ("lite", "standard", "performance"):
        return explicit

    if hw["cuda_available"] and hw["gpu_vram_gb"] >= 4.0:
        return "performance"
    if hw["ram_gb"] >= 16:
        return "performance"
    if hw["ram_gb"] >= 8:
        return "standard"
    return "lite"


def compute_config(hw: dict, profile: str) -> dict:
    """Compute optimal settings for the given hardware and profile."""
    config = {}

    if hw["cuda_available"] and hw["gpu_vram_gb"] >= 4.0:
        config["device"] = "cuda"
        # GPU handles concurrency natively — no need for CPU pool replicas
        config["SLOPTOTAL_TORCH_THREADS"] = "1"
        config["SLOPTOTAL_POOL_BERT_RAID"] = "1"
        config["SLOPTOTAL_POOL_E5"] = "1"
        config["SLOPTOTAL_POOL_FAKESPOT"] = "1"
        config["SLOPTOTAL_POOL_TMR"] = "1"
        config["SLOPTOTAL_SNIPPET_WORKERS"] = str(min(4, hw["cpu_count"]))
        config["SLOPTOTAL_FULL_WORKERS"] = str(min(8, hw["cpu_count"]))
    else:
        config["device"] = "cpu"
        config["SLOPTOTAL_TORCH_THREADS"] = "1"

        if profile == "performance":
            # 16GB+ RAM: can afford pool replicas
            usable = max(hw["cpu_count"] - 2, 2)
            pool = "2" if hw["ram_gb"] >= 32 else "1"
            config["SLOPTOTAL_POOL_BERT_RAID"] = pool
            config["SLOPTOTAL_POOL_E5"] = pool
            config["SLOPTOTAL_POOL_FAKESPOT"] = pool
            config["SLOPTOTAL_POOL_TMR"] = pool
            config["SLOPTOTAL_SNIPPET_WORKERS"] = str(min(4, usable))
            config["SLOPTOTAL_FULL_WORKERS"] = str(usable)
        elif profile == "standard":
            # 8-16GB: all engines, single copies
            usable = max(hw["cpu_count"] - 2, 2)
            config["SLOPTOTAL_POOL_BERT_RAID"] = "1"
            config["SLOPTOTAL_POOL_E5"] = "1"
            config["SLOPTOTAL_POOL_FAKESPOT"] = "1"
            config["SLOPTOTAL_POOL_TMR"] = "1"
            config["SLOPTOTAL_SNIPPET_WORKERS"] = str(min(3, usable))
            config["SLOPTOTAL_FULL_WORKERS"] = str(min(6, usable))
        else:
            # lite: minimal
            config["SLOPTOTAL_POOL_BERT_RAID"] = "1"
            config["SLOPTOTAL_POOL_E5"] = "1"
            config["SLOPTOTAL_POOL_FAKESPOT"] = "1"
            config["SLOPTOTAL_POOL_TMR"] = "1"
            config["SLOPTOTAL_SNIPPET_WORKERS"] = "2"
            config["SLOPTOTAL_FULL_WORKERS"] = "2"

    # Concurrency guards — relaxed for single-user, tight for multi-user
    if profile == "lite":
        config["SLOPTOTAL_MAX_CONCURRENT_FULL"] = "1"
        config["SLOPTOTAL_MAX_CONCURRENT_SNIPPET"] = "2"
    else:
        config["SLOPTOTAL_MAX_CONCURRENT_FULL"] = "2"
        config["SLOPTOTAL_MAX_CONCURRENT_SNIPPET"] = "4"

    # Reserved cores
    config["SLOPTOTAL_RESERVED_CORES"] = "2"

    # Lite mode flag — used by analyzer to skip heavy engines
    config["SLOPTOTAL_LITE"] = "1" if profile == "lite" else "0"

    return config


def apply_config(config: dict) -> None:
    """Set env vars for keys not already set. Explicit env vars always win."""
    for key, value in config.items():
        if key == "device":
            continue  # handled separately via get_device()
        if os.getenv(key) is None:
            os.environ[key] = value


# Cache the device after first detection
_device: str | None = None


def get_device() -> str:
    """Return 'cuda' or 'cpu'. Cached after first call."""
    global _device
    if _device is not None:
        return _device

    import torch

    explicit = os.getenv("SLOPTOTAL_DEVICE")
    if explicit and explicit in ("cuda", "cpu"):
        _device = explicit
    elif torch.cuda.is_available():
        _device = "cuda"
    else:
        _device = "cpu"
    return _device


def run_autoconfig() -> tuple[dict, str, dict]:
    """Detect hardware, choose profile, apply config. Returns (hw, profile, config)."""
    hw = detect_hardware()
    profile = choose_profile(hw)
    config = compute_config(hw, profile)
    apply_config(config)
    return hw, profile, config


def format_banner(hw: dict, profile: str, config: dict) -> str:
    """Format a startup banner summarizing the configuration."""
    lines = [
        "",
        "  ┌─────────────────────────────────────────────┐",
        "  │          SlopTotal — Self-Hosted             │",
        "  └─────────────────────────────────────────────┘",
        "",
        "  Hardware:",
        f"    CPU:  {hw['cpu_count']} cores",
        f"    RAM:  {hw['ram_gb']} GB",
    ]
    if hw["cuda_available"]:
        lines.append(f"    GPU:  {hw['gpu_name']} ({hw['gpu_vram_gb']} GB VRAM)")
    else:
        lines.append("    GPU:  none detected")

    lines.extend(
        [
            "",
            f"  Profile: {profile}",
            f"  Device:  {config.get('device', 'cpu')}",
            f"  Engines: {'4 (lite mode)' if config.get('SLOPTOTAL_LITE') == '1' else '21 (full)'}",
        ]
    )

    if config.get("device") != "cuda":
        pool = config.get("SLOPTOTAL_POOL_FAKESPOT", "1")
        lines.append(f"  Pools:   {pool}x replicas per hot-path engine")

    lines.extend(
        [
            "",
            "  Dashboard:  http://localhost:8000",
            "  API:        http://localhost:8000/api/quick-score",
            "",
        ]
    )
    return "\n".join(lines)
