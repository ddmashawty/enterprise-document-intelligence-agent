from __future__ import annotations

from pathlib import Path

from kaoyan.config import Settings, get_settings
from kaoyan.ingest.loaders import ParsedDocument, load_file
from kaoyan.ingest.ocr import NoOCR, get_ocr_backend
from kaoyan.ingest.redact import looks_personal, mask_notice_names, redact_document
from kaoyan.privacy import is_personal_file, is_within


def load_document(path: Path, settings: Settings | None = None) -> ParsedDocument:
    """Load a file for indexing / tools, applying the privacy policy.

    Files under the kaoyan data dir get PDF tables extracted; files flagged
    ``contains_personal_data`` in sources.json, or with a name + exam-number table,
    are redacted (李某, id columns dropped) before anything downstream sees them.
    Other kaoyan notices still get "拟录取X等N人" lead names masked.
    """
    s = settings or get_settings()
    kaoyan_file = is_within(path, s.kaoyan_data_path)
    personal = kaoyan_file and is_personal_file(path, s.kaoyan_data_path)
    # Scanned rosters are only counted (kaoyan.roster), never OCR'd into the index.
    ocr = NoOCR() if personal else get_ocr_backend(s.ocr_backend, s)
    doc = load_file(path, tables=kaoyan_file, ocr=ocr)
    if personal or looks_personal(doc.tables):
        doc = redact_document(doc)
    elif kaoyan_file:
        doc = mask_notice_names(doc)
    return doc
