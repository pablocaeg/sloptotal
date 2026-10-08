"""Keep literal application environment settings discoverable in the README."""

import re
from pathlib import Path


def test_application_environment_variables_are_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(
        r"""os\.(?:getenv|environ\.get)\(\s*["'](SLOPTOTAL_[A-Z0-9_]+)["']"""
    )
    variables = {
        name
        for source in (root / "app").rglob("*.py")
        for name in pattern.findall(source.read_text(encoding="utf-8"))
    }
    readme = (root / "README.md").read_text(encoding="utf-8")
    missing = sorted(name for name in variables if name not in readme)
    assert not missing, (
        f"Environment variables missing from README.md: {', '.join(missing)}"
    )
