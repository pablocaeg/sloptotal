# Third-Party Licenses

SlopTotal is licensed under the MIT License. Some dependencies have different licenses:

## GPL-3.0 Dependencies

### trafilatura

- **License**: GPL-3.0
- **Purpose**: HTML text extraction for URL scanning
- **Source**: https://github.com/adbar/trafilatura

This means that if you distribute a combined work (e.g., a Docker image containing SlopTotal and all its dependencies), that combined distribution must comply with the GPL-3.0 terms for trafilatura.

The SlopTotal source code itself remains MIT-licensed. When you install dependencies via `pip install -r requirements.txt`, you are downloading trafilatura separately under its own license.

## Apache-2.0 Dependencies

- **transformers** (Hugging Face): Apache-2.0
- **tokenizers**: Apache-2.0

## BSD Dependencies

- **fastapi**: BSD-3-Clause
- **uvicorn**: BSD-3-Clause
- **torch** (PyTorch): BSD-3-Clause

## MIT Dependencies

- **pydantic**: MIT
- **aiosqlite**: MIT
- **textstat**: MIT
- **httpx**: BSD-3-Clause

For a complete list of dependencies, see `requirements.txt`.
