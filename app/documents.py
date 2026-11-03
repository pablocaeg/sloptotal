"""Extract plain text from uploaded documents (PDF, Word, plain text).

Only the text is used: it is returned to the browser, which submits it like
pasted text, so uploads follow exactly the same analysis and retention path.
"""

import io

from app.config import MIN_TEXT_LENGTH

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED = (".pdf", ".docx", ".txt", ".md")


def extract_document_text(filename: str, data: bytes) -> str:
    """Return the text of an uploaded file, or raise ValueError."""
    name = (filename or "").lower()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File is larger than 10 MB.")
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages[:50]]
        except Exception as exc:
            raise ValueError("Could not read that PDF.") from exc
        text = "\n\n".join(p.strip() for p in pages if p.strip())
    elif name.endswith(".docx"):
        from docx import Document
        from docx.text.paragraph import Paragraph

        try:
            doc = Document(io.BytesIO(data))
        except Exception as exc:
            raise ValueError("Could not read that Word document.") from exc
        parts = []
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                paragraph_text = block.text.strip()
                if paragraph_text:
                    parts.append(paragraph_text)
                continue
            seen_cells = set()
            for row in block.rows:
                for cell in row.cells:
                    if cell._tc not in seen_cells:
                        seen_cells.add(cell._tc)
                        cell_text = cell.text.strip()
                        if cell_text:
                            parts.append(cell_text)
        text = "\n\n".join(parts)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError("Supported files: " + ", ".join(SUPPORTED))
    text = text.strip()
    if len(text) < MIN_TEXT_LENGTH:
        raise ValueError(
            "No readable text found. Scanned PDFs (images of pages) are not supported."
        )
    return text
