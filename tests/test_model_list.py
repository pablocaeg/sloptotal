"""Keep the model update inventory in sync without importing engine modules."""

import importlib.util
import re
from pathlib import Path

from app.config import GPT2_MODEL


def test_model_update_inventory_covers_engine_models() -> None:
    root = Path(__file__).resolve().parents[1]
    engines = root / "app" / "engines"
    pattern = re.compile(
        r"""^_(?:MODEL|BASE)_NAME\s*=\s*["']([^"']+)["']""", re.MULTILINE
    )
    model_ids = {
        model
        for source in engines.glob("*.py")
        for model in pattern.findall(source.read_text(encoding="utf-8"))
    }
    model_ids.add(GPT2_MODEL)
    cross_perplexity = (engines / "cross_perplexity.py").read_text(encoding="utf-8")
    model_ids.update(re.findall(r"""["'](distilgpt2)["']""", cross_perplexity))

    spec = importlib.util.spec_from_file_location(
        "check_model_updates", root / "scripts" / "check_model_updates.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    missing = sorted(model_ids - set(module.MODELS))
    assert not missing, (
        f"Model IDs missing from scripts/check_model_updates.py MODELS: {', '.join(missing)}"
    )
