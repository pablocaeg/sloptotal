"""Keep download and RAM docs aligned with docs/MODELS.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Claims that the first-run model download is about 2 GB (stale vs MODELS.md).
_STALE_TWO_GB_DOWNLOAD = re.compile(
    r"(?:"
    r"downloads?\s+(?:about\s+|~)?2\s*GB"
    r"|Models?\s*\(\s*~?\s*2\s*GB\s*\)"
    r"|about\s+2\s*GB\s+of\s+models"
    r"|~\s*2\s*GB\s+of\s+models"
    r")",
    re.IGNORECASE,
)


def test_no_markdown_claims_two_gb_model_download() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.md"):
        if any(part.startswith(".") and part != ".github" for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _STALE_TWO_GB_DOWNLOAD.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "Markdown still claims a 2 GB model download; use ~9 GB from "
        "docs/MODELS.md:\n" + "\n".join(offenders)
    )


def test_readme_ram_and_download_point_at_models_doc() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "4 GB RAM is enough" not in readme
    assert "about 9 GB of models" in readme
    assert "docs/MODELS.md" in readme
    assert "8.3 GB" in readme
