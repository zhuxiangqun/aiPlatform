#!/usr/bin/env python3
"""
Data-driven domain seeder — populates GraphIndex + Wiki from existing data files.

No hardcoded business content. All seed data comes from:
  - ~/.aiplat/ontologies/registry.json   → domain list
  - ~/.aiplat/ontologies/{domain}.yaml    → class names, descriptions
  - ~/.aiplat/seed_data/{domain}.json     → entity/relation data (optional)

Usage:
  python scripts/quick_seed.py                    # seed all active domains
  python scripts/quick_seed.py --domain lock-service  # seed one domain
  python scripts/quick_seed.py --dry-run          # show what would happen
"""
import argparse
import json
import os
import sys
import time

ONTOLOGIES_DIR = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
SEED_DIR = os.path.expanduser("~/.aiplat/seed_data")
WIKI_DIR = os.path.expanduser("~/.aiplat/wiki/collections")


def _load_registry():
    """Read registry.json → {domain_id: domain_cfg}."""
    path = os.path.join(ONTOLOGIES_DIR, "registry.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("domains", {})


def _load_ontology(domain_id: str) -> dict | None:
    """Read ~/.aiplat/ontologies/{domain_id}.yaml."""
    path = os.path.join(ONTOLOGIES_DIR, f"{domain_id}.yaml")
    if not os.path.isfile(path):
        return None
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_seed_json(domain_id: str) -> dict | None:
    """Read ~/.aiplat/seed_data/{domain_id}.json."""
    path = os.path.join(SEED_DIR, f"{domain_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_class_names(ontology: dict) -> list[str]:
    """Extract class key names from ontology YAML."""
    classes = ontology.get("classes", {})
    return list(classes.keys())


def _get_domain_description(ontology: dict) -> str:
    """Extract human-readable description from ontology."""
    desc = ontology.get("description", "")
    if desc:
        return desc

    classes = _get_class_names(ontology)
    if classes:
        return f"{ontology.get('name', 'Unknown')} 领域，包含以下概念：{'、'.join(classes[:5])}"
    return f"{ontology.get('name', 'Unknown')} 领域知识库"


def _get_class_descriptions(ontology: dict) -> list[tuple[str, str]]:
    """Return (class_name, description) pairs from ontology."""
    classes = ontology.get("classes", {})
    result = []
    for key, cfg in classes.items():
        label = cfg.get("label", key)
        desc = cfg.get("description", f"{label}的详细信息")
        result.append((key, f"## {label}\n\n{desc}"))
    return result


def seed_graph_from_json(domain_id: str, dry_run: bool = False) -> int:
    """Load entities + relations from seed_data JSON and write to GraphIndex."""
    data = _load_seed_json(domain_id)
    if not data:
        return 0

    if dry_run:
        entities = data.get("entities", [])
        relations = data.get("relations", [])
        print(f"  {domain_id}: [dry-run] {len(entities)} entities + {len(relations)} relations from seed JSON")
        return len(entities)

    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load(domain_id)

    for e in data.get("entities", []):
        cls = e.pop("class", e.pop("class_name", "Entity"))
        name = e.pop("name", str(e))
        props = e.pop("properties", {})  # nested properties object
        remaining = dict(e)  # any flat attributes left after popping class/name
        
        eid = f"{domain_id}_{name.replace(' ', '_').replace('/', '_')[:60]}"
        g.add_entity(eid, name, cls, source_doc_id=domain_id)

        # Write nested properties
        for key, value in props.items():
            if value is not None:
                g.add_entity_property(eid, key, value)
        # Write any remaining flat attributes (backward compat)
        for key, value in remaining.items():
            if value is not None and key not in ("class_name", "id"):
                g.add_entity_property(eid, key, value)

    for r in data.get("relations", []):
        # Support both source/type/target (new format) and subject/predicate/object (legacy)
        subj = r.get("source") or r.get("subject", "")
        obj = r.get("target") or r.get("object", "")
        pred = r.get("type") or r.get("predicate", "related_to")
        sid = f"{domain_id}_{subj.replace(' ', '_')[:60]}"
        oid = f"{domain_id}_{obj.replace(' ', '_')[:60]}"
        try:
            g.add_relation(sid, oid, pred, relation_label=pred, confidence=0.85)
        except Exception:
            pass

    count = len(g._nodes)
    print(f"  {domain_id}: {len(data.get('entities', []))} entities + "
          f"{len(data.get('relations', []))} relations → {count} graph nodes")
    return count


def seed_graph_minimal(domain_id: str, ontology: dict, dry_run: bool = False) -> int:
    """Create 2 minimal entities using ontology's own class names."""
    classes = _get_class_names(ontology)
    if not classes:
        return 0

    primary_class = classes[0]
    secondary_class = classes[1] if len(classes) > 1 else classes[0]

    if dry_run:
        print(f"  {domain_id}: [dry-run] 2 minimal entities (classes: {primary_class}, {secondary_class})")
        return 2

    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load(domain_id)
    domain_name = ontology.get("name", domain_id)

    g.add_entity(
        f"{domain_id}_e1", f"{domain_name} 核心实体",
        primary_class, source_doc_id="quick-seed",
    )
    g.add_entity(
        f"{domain_id}_e2", f"{domain_name} 辅助实体",
        secondary_class, source_doc_id="quick-seed",
    )
    count = len(g._nodes)
    print(f"  {domain_id}: minimal seed ({primary_class} + {secondary_class}) → {count} nodes")
    return count


def seed_wiki_pages(domain_id: str, ontology: dict, dry_run: bool = False) -> int:
    """Generate Wiki pages from ontology description and class definitions."""
    import yaml
    collection_dir = os.path.join(WIKI_DIR, domain_id)
    os.makedirs(collection_dir, exist_ok=True)

    pages_to_write = []

    # Page 1: domain overview (from ontology description)
    overview = _get_domain_description(ontology)
    pages_to_write.append(("领域概述", overview))

    # Pages 2+: one per class (from ontology label + description)
    for class_name, content in _get_class_descriptions(ontology):
        safe_title = class_name.replace(" ", "_").replace("/", "_")[:60]
        pages_to_write.append((safe_title, content))

    if dry_run:
        print(f"  {domain_id}: [dry-run] {len(pages_to_write)} wiki pages would be created")
        return len(pages_to_write)

    created = 0
    for title, content in pages_to_write:
        safe_name = title.replace(" ", "_").replace("/", "_")[:80]
        # Wiki engine searches *.md inside category subdirectories, not root
        category_dir = os.path.join(collection_dir, "entities")
        os.makedirs(category_dir, exist_ok=True)
        page_path = os.path.join(category_dir, f"{safe_name}.md")

        if not os.path.exists(page_path):
            frontmatter = yaml.dump({
                "title": title,
                "domain_id": domain_id,
                "effective_date": time.strftime("%Y-%m-%d"),
                "marking": "public",
                "version": "1.0.0",
                "tags": ["seed", domain_id],
            }, allow_unicode=True, sort_keys=False)
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(f"---\n{frontmatter}---\n\n{content}\n")
            created += 1

        # Always register in index.json (even for pre-existing pages)
        _register_in_index(domain_id, title, ["seed", domain_id])

    if created:
        print(f"  {domain_id}: {created} wiki pages from ontology definitions")
    return created


def _register_in_index(domain_id: str, title: str, tags: list[str]):
    """Add a page entry to the collection's index.json."""
    index_path = os.path.join(WIKI_DIR, domain_id, "index.json")
    index = {}
    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            pass

    pages = index.get("pages", {})
    pages[title] = {
        "category": "entities",
        "tags": tags,
        "related": [],
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    index["pages"] = pages
    index.setdefault("last_updated", time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def seed_domain(domain_id: str, dry_run: bool = False) -> tuple[int, int]:
    """Seed one domain: entities to GraphIndex, wiki pages from ontology."""
    ontology = _load_ontology(domain_id)
    if not ontology:
        print(f"  {domain_id}: no ontology YAML, skipping")
        return 0, 0

    has_seed_json = _load_seed_json(domain_id) is not None
    if has_seed_json:
        entity_count = seed_graph_from_json(domain_id, dry_run)
    else:
        entity_count = seed_graph_minimal(domain_id, ontology, dry_run)

    wiki_count = seed_wiki_pages(domain_id, ontology, dry_run)
    return entity_count, wiki_count


def main():
    parser = argparse.ArgumentParser(description="Data-driven domain seeder")
    parser.add_argument("--domain", type=str, help="Seed a specific domain")
    parser.add_argument("--all", action="store_true", help="Seed all registered domains (default)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    args = parser.parse_args()

    registry = _load_registry()
    all_domain_ids = list(registry.keys())

    if args.domain:
        domains = [args.domain]
    else:
        # Default: seed all registered domains
        domains = sorted(all_domain_ids)

    if not domains:
        if all_domain_ids:
            print("No domains selected. Use --all to seed all registered domains.")
        else:
            print("No domains found in registry.json. Add domains first.")
        return

    print(f"Seeding {len(domains)} domain(s): {', '.join(domains)}")
    if args.dry_run:
        print("(dry-run mode — no changes will be made)\n")

    total_entities = 0
    total_wiki = 0

    for domain_id in domains:
        print(f"\n[{domain_id}]")
        try:
            e, w = seed_domain(domain_id, dry_run=args.dry_run)
            total_entities += e
            total_wiki += w
        except Exception as exc:
            print(f"  ERROR: {exc}")

    mode = "[dry-run] " if args.dry_run else ""
    print(f"\n{mode}Done: {total_entities} entities, {total_wiki} wiki pages across {len(domains)} domains")


if __name__ == "__main__":
    main()
