from __future__ import annotations

from doc_agent.ingest.chunking import _split_text, chunk_document
from doc_agent.ingest.loaders import DocumentPage, LoadedDocument


def test_split_text_overlap():
    parts = _split_text("abcdefghij", chunk_size=4, overlap=1)
    assert parts[0] == "abcd"
    assert len(parts) >= 2
    assert "".join(p[0] for p in parts)  # non-empty


def test_chunk_document_ids():
    doc = LoadedDocument(
        source="/tmp/demo.txt",
        pages=[DocumentPage(source="/tmp/demo.txt", page=1, text="hello world " * 50)],
    )
    chunks = chunk_document(doc, chunk_size=40, overlap=5)
    assert chunks
    assert chunks[0].doc_name == "demo.txt"
    assert chunks[0].chunk_id.startswith("demo.txt::p1::")
