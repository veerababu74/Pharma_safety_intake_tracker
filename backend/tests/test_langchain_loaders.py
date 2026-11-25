from pathlib import Path

import pytest

from app.modules.loaders.langchain_loaders import load_uploaded_document


def test_text_loader(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("Quarantine LOT-88392 within 4 business hours.", encoding="utf-8")
    loaded = load_uploaded_document(p)
    assert loaded.loader_name == "TextLoader"
    assert "LOT-88392" in loaded.text
    assert len(loaded.pages) >= 1


def test_csv_loader(tmp_path: Path):
    p = tmp_path / "solutions.csv"
    p.write_text(
        "solution_id,issue_keyword,recommended_intake_action\n"
        "SOL-001,broken seal,Quarantine lot and notify Quality Desk\n",
        encoding="utf-8",
    )
    loaded = load_uploaded_document(p)
    assert loaded.loader_name == "CSVLoader"
    assert "broken seal" in loaded.text.lower() or "Quarantine" in loaded.text


def test_unsupported_extension(tmp_path: Path):
    p = tmp_path / "image.png"
    p.write_bytes(b"not-an-image")
    with pytest.raises(ValueError, match="Unsupported"):
        load_uploaded_document(p)
