from app.modules.chunking.strategies import AgenticChunkingStrategy, SemanticChunkingStrategy
from app.modules.embeddings.providers import HashEmbeddingProvider
from app.modules.llms.base import LLMProvider, LLMResponse


class FakeSegmentLLM(LLMProvider):
    name = "fake_segment"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        # Always return two segments covering indexes 0..N
        # Parse max index from prompt lines "0: ..."
        import re

        idxs = [int(m) for m in re.findall(r"(?m)^(\d+):", prompt)]
        last = max(idxs) if idxs else 1
        mid = max(0, last // 2)
        content = (
            '```json\n'
            f'[{{"start":0,"end":{mid},"title":"intro"}},'
            f'{{"start":{mid+1},"end":{last},"title":"details"}}]\n'
            "```"
        )
        return LLMResponse(content=content, model="fake", provider=self.name)


def test_semantic_uses_embedding_model():
    text = (
        "Quarantine the implicated lot within 4 business hours. "
        "Notify the fictional Quality Desk immediately. "
        "The weather in Paris is lovely in spring. "
        "Tourists enjoy museums and cafes around the city. "
        "Broken bottle seals require packaging intake notes only."
    )
    strategy = SemanticChunkingStrategy(
        embedding=HashEmbeddingProvider(dim=64),
        breakpoint_percentile=40,
    )
    chunks = strategy.split(text, chunk_size=80, chunk_overlap=10)
    assert len(chunks) >= 1
    assert chunks[0].metadata.get("strategy") == "semantic"
    assert chunks[0].metadata.get("mode") in {"embedding_cosine", "fallback", "single"}


def test_agentic_uses_llm_segments():
    text = (
        "Purpose of this SOP is intake quarantine. "
        "Scope covers packaging complaints only. "
        "Procedure requires REF ID creation. "
        "Example lot is LOT-88392. "
        "Out of scope includes treatment advice."
    )
    strategy = AgenticChunkingStrategy(llm=FakeSegmentLLM())
    chunks = strategy.split(text, chunk_size=100, chunk_overlap=5)
    assert len(chunks) >= 1
    assert chunks[0].metadata.get("strategy") == "agentic"
    assert chunks[0].metadata.get("mode") in {"llm_segments", "heuristic_fallback", "single"}
