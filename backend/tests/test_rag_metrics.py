from app.modules.rag.pipeline import HybridRAGPipeline, RetrievedChunk
from app.modules.rag.query_expansion import QueryExpansionService
from app.modules.llms.base import LLMProvider, LLMResponse
from evaluation.metrics import precision_at_k, recall_at_k, mrr


def test_rrf_fusion_orders_overlap_higher():
    sparse = [
        RetrievedChunk("a", "text a", 10, {}),
        RetrievedChunk("b", "text b", 9, {}),
    ]
    dense = [
        RetrievedChunk("b", "text b", 0.9, {}),
        RetrievedChunk("c", "text c", 0.8, {}),
    ]
    fused = HybridRAGPipeline._rrf_many([sparse, dense], k=60)
    assert fused[0].chunk_id == "b"


def test_basic_retrieval_metrics():
    retrieved = ["a", "b", "c"]
    relevant = ["b", "z"]
    assert precision_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 3) == 0.5
    assert mrr(retrieved, relevant) == 0.5


class JsonMultiLLM(LLMProvider):
    name = "json_multi"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        if "Enhance" in prompt or "enhanced" in (system or "").lower() or "Enhance this" in prompt:
            return LLMResponse(
                content="packaging complaint LOT-88392 quarantine SOP intake steps",
                model="fake",
                provider=self.name,
            )
        return LLMResponse(
            content='["alt query one about LOT-88392","alt query two quarantine","alt query three seal broken"]',
            model="fake",
            provider=self.name,
        )


def test_query_expansion_returns_up_to_five():
    svc = QueryExpansionService(JsonMultiLLM())
    expanded = svc.expand("broken seal LOT-88392", enable_enhancer=True, enable_multi=True, multi_count=3)
    queries = expanded.all_queries
    assert expanded.original
    assert expanded.enhanced
    assert len(expanded.multi_queries) == 3
    assert 2 <= len(queries) <= 5
