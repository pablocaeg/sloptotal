"""Extract plain text from uploaded documents (PDF, Word, plain text).

Only the text is used: it is returned to the browser, which submits it like
pasted text, so uploads follow exactly the same analysis and retention path.
"""

import io

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

        try:
            doc = Document(io.BytesIO(data))
        except Exception as exc:
            raise ValueError("Could not read that Word document.") from exc
        text = "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError("Supported files: " + ", ".join(SUPPORTED))
    text = text.strip()
    if len(text) < 50:
        raise ValueError(
            "No readable text found. Scanned PDFs (images of pages) are not supported."
        )
    return text
