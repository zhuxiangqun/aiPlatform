#!/usr/bin/env python3
"""CLI for RAG evaluation — usable in CI/CD pipelines.

Usage:
  python scripts/rag_eval_cli.py --tag budget --threshold 0.7
  python scripts/rag_eval_cli.py --all --threshold 0.8

Exit codes:
  0 = all metrics above threshold
  1 = evaluation failed or metrics below threshold
"""
import argparse, json, sys, time

API = "http://localhost:8002/api/core/kb-eval"

def fetch_samples(tag=None):
    import urllib.request
    url = f"{API}/samples?limit=50"
    if tag: url += f"&tag={tag}"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

def run_eval(sample_ids=None, tag=None):
    import urllib.request
    body = {"sample_ids": sample_ids} if sample_ids else {"tag": tag}
    req = urllib.request.Request(f"{API}/run", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def main():
    p = argparse.ArgumentParser(description="RAG Evaluation CLI")
    p.add_argument("--tag", help="Filter samples by tag")
    p.add_argument("--all", action="store_true", help="Evaluate all samples")
    p.add_argument("--threshold", type=float, default=0.7, help="Minimum avg faithfulness threshold")
    args = p.parse_args()

    sample_ids = None
    tag = args.tag if not args.all else None
    print(f"Running RAG evaluation... tag={tag} threshold={args.threshold}")

    result = run_eval(sample_ids=sample_ids, tag=tag)
    if result.get("reports", 0) == 0:
        print("No samples found or evaluation produced no results")
        sys.exit(1)

    avg = result.get("avg_metrics", {})
    faith = avg.get("faithfulness", 0)
    print(f"Reports: {result['reports']}")
    print(f"Faithfulness: {faith:.3f}  AnswerRelevancy: {avg.get('answer_relevancy',0):.3f}  ContextPrecision: {avg.get('context_precision',0):.3f}  ContextRecall: {avg.get('context_recall',0):.3f}")
    print(f"Failures: {result.get('failure_distribution', {})}")

    if faith < args.threshold:
        print(f"❌ FAIL: faithfulness {faith:.3f} < threshold {args.threshold}")
        sys.exit(1)
    else:
        print(f"✅ PASS: faithfulness {faith:.3f} >= threshold {args.threshold}")
        sys.exit(0)

if __name__ == "__main__":
    main()
