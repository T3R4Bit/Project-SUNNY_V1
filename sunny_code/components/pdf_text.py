"""Extracts text from a PDF file's raw bytes -- e.g. a syllabus sent as a
Discord attachment instead of pasted as text (see discord_bot.py's
on_message, the only caller today, since it's the only interface with a
file-upload mechanism; class_setup_engine.py is the first real consumer
of the extracted text).

Text-layer extraction only -- a scanned syllabus with no real text layer
(just images of pages) comes back empty, same as a corrupt or encrypted-
with-a-real-password file. No OCR; out of scope until something actually
needs it.
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CHARS = 20_000  # keeps one pathological PDF from blowing up a prompt


def extract_text(pdf_bytes: bytes) -> Optional[str]:
    """Returns extracted text (truncated to MAX_CHARS), or None if nothing
    usable could be pulled out -- corrupt file, wrong format despite a
    .pdf name, real password protection, or a scanned/image-only PDF with
    no text layer. Never raises; same fail-quiet contract as everything
    else here."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("extract_text: pypdf not installed")
        return None

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            # Some PDFs are flagged encrypted but only "owner" (permissions)
            # restricted, not actually password-protected for reading --
            # an empty password unlocks those; a real password doesn't.
            try:
                reader.decrypt("")
            except Exception:
                return None
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        logger.warning(f"extract_text: failed to read PDF: {e}")
        return None

    text = text.strip()
    if not text:
        return None
    return text[:MAX_CHARS]
