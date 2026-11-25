"""Local storage path traversal and filename safety."""

from __future__ import annotations

import pytest

from app.modules.storage.local import LocalObjectStorage
from app.services.document_service import _safe_filename


def test_safe_filename_blocks_traversal():
    assert _safe_filename("sop.txt") == "sop.txt"
    assert _safe_filename(r"..\..\windows\system32\x.txt") == "x.txt"
    with pytest.raises(ValueError):
        _safe_filename("..")
    with pytest.raises(ValueError):
        _safe_filename("")


def test_local_storage_rejects_escape(tmp_path):
    store = LocalObjectStorage(str(tmp_path))
    store.save("DOC-1/ok.txt", b"hello")
    with pytest.raises(ValueError):
        store.save("../escape.txt", b"nope")
    with pytest.raises(ValueError):
        store.save("DOC-1/../../escape.txt", b"nope")
