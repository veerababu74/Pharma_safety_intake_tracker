from app.auth.seed import SAMPLE_USERS
from app.services.document_service import DuplicateDocumentError, sha256_bytes, sha256_text


def test_two_users_per_role():
    roles = {}
    for u in SAMPLE_USERS:
        roles.setdefault(u["role"], []).append(u["username"])
    assert set(roles) == {"admin", "reviewer", "operator", "approver"}
    assert all(len(users) == 2 for users in roles.values())
    assert len(SAMPLE_USERS) == 8


def test_file_and_chunk_hash_stable():
    data = b"hello fictional sop"
    assert sha256_bytes(data) == sha256_bytes(data)
    assert len(sha256_bytes(data)) == 64
    assert sha256_text("same") == sha256_text("same")
    assert sha256_text("same") != sha256_text("different")


def test_duplicate_document_error_payload():
    err = DuplicateDocumentError("DOC-ABC", "a" * 64)
    assert err.existing_doc_id == "DOC-ABC"
    assert "Duplicate file" in str(err)
