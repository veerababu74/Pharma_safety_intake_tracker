"""Hybrid RAG: query expansion (5 queries) + BM25 + dense + RRF + rerank."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.modules.embeddings.base import EmbeddingProvider
from app.modules.llms.base import LLMProvider
from app.modules.rag.prompts import RAG_ANSWER_SYSTEM, build_rag_answer_prompt
from app.modules.rag.query_expansion import QueryExpansionService
from app.modules.rag.reranker import Reranker, create_reranker
from app.modules.tracing.base import Tracer
from app.modules.vectorstores.base import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9\-]+", text.lower())


class HybridRAGPipeline:
    def __init__(
        self,
        embedding: EmbeddingProvider,
        vector_store: VectorStore,
        llm: LLMProvider,
        tracer: Tracer,
        reranker: Reranker | None = None,
        query_enhancer_llm: LLMProvider | None = None,
        query_rewrite_llm: LLMProvider | None = None,
    ) -> None:
        self.embedding = embedding
        self.vector_store = vector_store
        self.llm = llm  # RAG answer generation role
        self.tracer = tracer
        self.query_expansion = QueryExpansionService(
            enhancer_llm=query_enhancer_llm or llm,
            rewrite_llm=query_rewrite_llm or query_enhancer_llm or llm,
        )
        settings = get_settings()
        self.reranker = reranker or create_reranker(
            provider=settings.reranker_provider,
            embedding=embedding,
            model_name=settings.reranker_model_name,
        )
        self._bm25_docs: list[str] = []
        self._bm25_ids: list[str] = []
        self._bm25_meta: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None

    def rebuild_bm25(self, texts: list[str], ids: list[str], metas: list[dict[str, Any]]) -> None:
        self._bm25_docs = texts
        self._bm25_ids = ids
        self._bm25_meta = metas
        tokenized = [_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(tokenized, k1=1.35, b=0.75) if tokenized else None

    def _bm25_search(self, query: str, top_k: int = 50) -> list[RetrievedChunk]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                chunk_id=self._bm25_ids[i],
                text=self._bm25_docs[i],
                score=float(score),
                metadata=self._bm25_meta[i],
            )
            for i, score in ranked
            if score > 0
        ]

    def _dense_search(self, query: str, top_k: int = 50) -> list[RetrievedChunk]:
        emb = self.embedding.embed_query(query)
        hits = self.vector_store.similarity_search(emb, top_k=top_k)
        return [
            RetrievedChunk(chunk_id=h.id, text=h.text, score=h.score, metadata=h.metadata)
            for h in hits
        ]

    @staticmethod
    def _rrf_many(result_lists: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
        scores: dict[str, float] = defaultdict(float)
        payload: dict[str, RetrievedChunk] = {}
        for results in result_lists:
            for rank, item in enumerate(results, start=1):
                scores[item.chunk_id] += 1.0 / (k + rank)
                payload[item.chunk_id] = item
        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            RetrievedChunk(
                chunk_id=cid,
                text=payload[cid].text,
                score=score,
                metadata=payload[cid].metadata,
            )
            for cid, score in ordered
        ]

    def _search_all_queries(
        self, queries: list[str], top_k: int = 50
    ) -> tuple[list[list[RetrievedChunk]], list[list[RetrievedChunk]], list[RetrievedChunk]]:
        sparse_lists: list[list[RetrievedChunk]] = []
        dense_lists: list[list[RetrievedChunk]] = []
        for q in queries:
            sparse_lists.append(self._bm25_search(q, top_k=top_k))
            dense_lists.append(self._dense_search(q, top_k=top_k))
        fused = self._rrf_many([*sparse_lists, *dense_lists], k=60)
        return sparse_lists, dense_lists, fused

    def _rerank(
        self, query: str, candidates: list[RetrievedChunk], top_n: int = 5
    ) -> list[RetrievedChunk]:
        settings = get_settings()
        payload = [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "score": c.score,
                "metadata": c.metadata,
            }
            for c in candidates
        ]
        payload = payload[: settings.rerank_candidate_limit]
        ranked = self.reranker.rerank(
            query,
            payload,
            top_n=top_n,
            score_threshold=settings.rerank_score_threshold,
        )
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                text=r["text"],
                score=float(r["score"]),
                metadata={**(r.get("metadata") or {}), "rerank_method": r.get("rerank_method")},
            )
            for r in ranked
        ]

    def query(
        self,
        question: str,
        *,
        actor: str | None = None,
        role: str | None = None,
        top_n: int = 5,
    ) -> dict[str, Any]:
        settings = get_settings()
        llm_cfg = settings.resolve_llm_role("rag")
        system = RAG_ANSWER_SYSTEM
        with self.tracer.span(
            "hybrid_rag_query",
            kind="retrieval",
            actor=actor,
            role=role,
            input_preview=question,
            metadata={
                "flow": "rag",
                "vector_store": settings.vector_store_provider,
                "embedding_provider": settings.embedding_provider,
                "embedding_model": settings.embedding_model_name,
                "top_n": top_n,
            },
        ) as root:
            # 1) Expand queries
            t0 = time.perf_counter()
            with self.tracer.span(
                "query_expansion",
                kind="span",
                actor=actor,
                role=role,
                input_preview=question,
                parent=root,
                metadata={"flow": "rag", "step": "expansion"},
            ) as exp_span:
                expanded = self.query_expansion.expand(
                    question,
                    enable_enhancer=settings.rag_query_enhancer_enabled,
                    enable_multi=settings.rag_multi_query_enabled,
                    multi_count=settings.rag_multi_query_count,
                )
                queries = expanded.all_queries
                exp_span.set_output(
                    {
                        "original": expanded.original,
                        "enhanced": expanded.enhanced,
                        "multi_queries": expanded.multi_queries,
                        "all_queries": queries,
                    }
                )
                exp_span.update(
                    query_count=len(queries),
                    enhancer_enabled=settings.rag_query_enhancer_enabled,
                    multi_enabled=settings.rag_multi_query_enabled,
                )
            expansion_ms = (time.perf_counter() - t0) * 1000

            # 2) Hybrid retrieval
            t1 = time.perf_counter()
            with self.tracer.span(
                "hybrid_retrieval",
                kind="retrieval",
                actor=actor,
                role=role,
                input_preview=str(queries),
                parent=root,
                metadata={"flow": "rag", "step": "retrieve", "query_count": len(queries)},
            ) as ret_span:
                sparse_lists, dense_lists, fused = self._search_all_queries(queries, top_k=50)
                sparse_hit_count = sum(len(x) for x in sparse_lists)
                dense_hit_count = sum(len(x) for x in dense_lists)
                ret_span.set_output(
                    {
                        "fused_top": [
                            {"chunk_id": c.chunk_id, "score": round(c.score, 4)} for c in fused[:15]
                        ],
                        "bm25_hit_total": sparse_hit_count,
                        "dense_hit_total": dense_hit_count,
                        "fused_count": len(fused),
                    }
                )
                ret_span.update(
                    bm25_hit_total=sparse_hit_count,
                    dense_hit_total=dense_hit_count,
                    fused_count=len(fused),
                )
            retrieve_ms = (time.perf_counter() - t1) * 1000

            # 3) Rerank
            t2 = time.perf_counter()
            with self.tracer.span(
                "rerank",
                kind="span",
                actor=actor,
                role=role,
                input_preview=question,
                parent=root,
                metadata={
                    "flow": "rag",
                    "step": "rerank",
                    "candidate_count": len(fused),
                    "reranker": getattr(self.reranker, "name", "unknown"),
                },
            ) as rr_span:
                final = self._rerank(question, fused, top_n=top_n)
                sources_compact = [
                    {
                        "chunk_id": c.chunk_id,
                        "score": round(c.score, 4),
                        "doc_id": c.metadata.get("doc_id"),
                        "rerank_method": c.metadata.get("rerank_method"),
                        "text_preview": (c.text or "")[:240],
                    }
                    for c in final
                ]
                rr_span.set_output(sources_compact)
                rr_span.update(
                    reranked_count=len(final),
                    reranker=getattr(self.reranker, "name", "unknown"),
                    threshold=settings.rerank_score_threshold,
                )
            rerank_ms = (time.perf_counter() - t2) * 1000

            context = "\n\n".join(
                f"[{i+1}] doc={c.metadata.get('doc_id')} chunk={c.chunk_id}\n{c.text}"
                for i, c in enumerate(final)
            )
            prompt = build_rag_answer_prompt(question=question, context=context)

            # 4) LLM answer
            t3 = time.perf_counter()
            with self.tracer.span(
                "rag_llm_generation",
                kind="generation",
                actor=actor,
                role=role,
                input_preview=prompt[:1500],
                parent=root,
                metadata={
                    "flow": "rag",
                    "step": "generation",
                    "llm_role": "rag",
                    "llm_provider": llm_cfg["provider"],
                    "llm_model": llm_cfg["model"],
                    "context_chunk_count": len(final),
                },
            ) as gen_span:
                llm_resp = self.llm.generate(prompt, system=system)
                gen_span.set_output(llm_resp.content)
                gen_span.update(
                    llm_provider=llm_resp.provider,
                    llm_model=llm_resp.model,
                    answer_chars=len(llm_resp.content or ""),
                )
            gen_ms = (time.perf_counter() - t3) * 1000

            result = {
                "answer": llm_resp.content,
                "sources": [
                    {
                        "chunk_id": c.chunk_id,
                        "score": c.score,
                        "doc_id": c.metadata.get("doc_id"),
                        "text": c.text[:400],
                        "rerank_method": c.metadata.get("rerank_method"),
                    }
                    for c in final
                ],
                "query_expansion": {
                    "original": expanded.original,
                    "enhanced": expanded.enhanced,
                    "multi_queries": expanded.multi_queries,
                    "all_queries_searched": queries,
                    "query_count": len(queries),
                },
                "diagnostics": {
                    "bm25_hit_total": sparse_hit_count,
                    "dense_hit_total": dense_hit_count,
                    "fused_count": len(fused),
                    "reranked_count": len(final),
                    "reranker": getattr(self.reranker, "name", "unknown"),
                    "llm_provider": llm_resp.provider,
                    "llm_model": llm_resp.model,
                    "latency_ms": {
                        "expansion": round(expansion_ms, 2),
                        "retrieve": round(retrieve_ms, 2),
                        "rerank": round(rerank_ms, 2),
                        "generation": round(gen_ms, 2),
                        "total": round(expansion_ms + retrieve_ms + rerank_ms + gen_ms, 2),
                    },
                },
            }
            root.set_output(
                {
                    "answer_preview": (llm_resp.content or "")[:1000],
                    "source_ids": [c.chunk_id for c in final],
                    "query_count": len(queries),
                }
            )
            root.update(
                llm_provider=llm_resp.provider,
                llm_model=llm_resp.model,
                retrieved_chunks=[c.chunk_id for c in final],
                source_count=len(final),
                latency_breakdown_ms=result["diagnostics"]["latency_ms"],
            )
            return result
