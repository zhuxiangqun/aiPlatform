#!/usr/bin/env python3
"""
Ingest seed data into ontology engine — Phase B2.

Usage:
  python scripts/ingest_seed.py --domain supply-chain
  python scripts/ingest_seed.py --all
  python scripts/ingest_seed.py --domain supply-chain --base-url http://localhost:8000

Requires: server running on base_url/api/core.
Seed data must be generated first: python scripts/seed_wiki.py --all
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

SEED_DIR = os.path.expanduser("~/.aiplat/seed_data")
API_PREFIX = "/api/core"


def post_json(url: str, data: dict, timeout: int = 60) -> dict:
    """POST JSON and return parsed response."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        return {"error": True, "status": e.code, "body": body}
    except Exception as e:
        return {"error": True, "message": str(e)}


def ingest_domain(base_url: str, domain_id: str) -> bool:
    """Ingest seed data for one domain via process-and-write API."""
    seed_path = os.path.join(SEED_DIR, f"{domain_id}.json")
    if not os.path.isfile(seed_path):
        print(f"  ⚠ No seed file for '{domain_id}', skipping")
        return False

    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    entities = data.get("entities", [])
    relations = data.get("relations", [])
    print(f"  {domain_id}: {len(entities)} entities, {len(relations)} relations")

    url = f"{base_url}{API_PREFIX}/ontology/engine/process-and-write"
    payload = {
        "domain_id": domain_id,
        "entities": entities,
        "relations": relations,
        "collection_id": domain_id,
        "description": data.get("description", ""),
    }

    print(f"    POST {url} ... ", end="", flush=True)
    start = time.time()
    result = post_json(url, payload, timeout=120)
    elapsed = time.time() - start

    if result.get("error"):
        print(f"FAILED ({elapsed:.1f}s): {result.get('status', '?')} {result.get('message', result.get('body', '')[:100])}")
        return False
    else:
        status = result.get("status", "ok")
        entities_processed = result.get("entities_processed", result.get("entity_count", "?"))
        print(f"DONE ({elapsed:.1f}s): status={status}, entities={entities_processed}")
        return True


def verify_domain(base_url: str, domain_id: str) -> bool:
    """Verify seed data landed in GraphIndex."""
    url = f"{base_url}{API_PREFIX}/ontology/engine/graph-stats/{domain_id}"
    try:
        result = post_json(url, {}, timeout=10)
        if result.get("error"):
            print(f"    Verify: API returned error")
            return False
        node_count = result.get("entity_count", result.get("node_count", "?"))
        edge_count = result.get("edge_count", result.get("relation_count", "?"))
        print(f"    GraphIndex: {node_count} entities, {edge_count} edges")
        return True
    except Exception as e:
        print(f"    Verify: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Ingest domain seed data into ontology engine")
    parser.add_argument("--domain", help="Single domain ID")
    parser.add_argument("--all", action="store_true", help="Ingest all domains with seed data")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--skip-verify", action="store_true", help="Skip post-ingest verification")
    args = parser.parse_args()

    if args.all:
        targets = []
        for f in sorted(os.listdir(SEED_DIR)):
            if f.endswith(".json"):
                targets.append(f[:-5])
    elif args.domain:
        targets = [args.domain]
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Ingesting {len(targets)} domain(s) to {args.base_url}{API_PREFIX}\n")
    ok = 0
    fail = 0
    for domain_id in targets:
        if ingest_domain(args.base_url, domain_id):
            ok += 1
            if not args.skip_verify:
                verify_domain(args.base_url, domain_id)
        else:
            fail += 1
        print()

    print(f"Done: {ok} OK, {fail} FAILED")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
