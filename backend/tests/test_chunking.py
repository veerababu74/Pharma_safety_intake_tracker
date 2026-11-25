from app.modules.chunking.strategies import get_chunking_strategy, list_chunking_strategies


def test_strategies_available():
    names = list_chunking_strategies()
    for expected in ["recursive", "semantic", "structure_aware", "agentic", "page_based"]:
        assert expected in names


def test_recursive_chunking():
    text = " ".join([f"word{i}" for i in range(200)])
    chunks = get_chunking_strategy("recursive").split(text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].index == 0


def test_page_based_chunking():
    pages = ["page one content here", "page two content here"]
    chunks = get_chunking_strategy("page_based").split(
        "\n".join(pages), chunk_size=20, chunk_overlap=0, pages=pages
    )
    assert any(c.page_number == 1 for c in chunks)
    assert any(c.page_number == 2 for c in chunks)
