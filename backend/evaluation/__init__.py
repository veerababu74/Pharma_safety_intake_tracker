"""Offline evaluation package for RAG and agents.

Classic metrics: precision/recall/MRR/nDCG/F1/grounding/refusal
RAGAS metrics: faithfulness, answer_relevancy, context_precision/recall, answer_correctness

Run:
  python -m evaluation.run_eval --mode both
  python -m evaluation.run_eval --mode ragas --force-heuristic
"""
