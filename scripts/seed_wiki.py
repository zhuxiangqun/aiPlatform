#!/usr/bin/env python3
"""Seed data generator for domain ontology — Phase B2.

Usage:  python scripts/seed_wiki.py --domain supply-chain --count 20
        python scripts/seed_wiki.py --all --count 15

Generates structured JSON payloads for POST /ontology/engine/process-and-write
and saves to ~/.aiplat/seed_data/{domain}.json for review before ingestion.
"""

import os, json, sys, argparse

SEED_DIR = os.path.expanduser("~/.aiplat/seed_data")
os.makedirs(SEED_DIR, exist_ok=True)

# ── Domain seed templates ──────────────────────────────────────────

SUPPLY_CHAIN_SEEDS = {
    "entities": [
        {"class": "Supplier", "name": "华东钢铁集团", "country": "中国", "tier": 1,
         "capacity": 50000, "lead_time_days": 14, "certifications": ["ISO9001", "IATF16949"]},
        {"class": "Supplier", "name": "日立金属", "country": "日本", "tier": 1,
         "capacity": 30000, "lead_time_days": 30, "certifications": ["ISO9001", "JIS"]},
        {"class": "Supplier", "name": "宝钢股份", "country": "中国", "tier": 2,
         "capacity": 80000, "lead_time_days": 10, "certifications": ["ISO9001"]},
        {"class": "Material", "name": "304不锈钢板", "category": "原材料",
         "specification": "2mm厚 冷轧", "min_order_qty": 100},
        {"class": "Material", "name": "SKD11模具钢", "category": "原材料",
         "specification": "淬火硬度HRC60-62", "min_order_qty": 50},
        {"class": "Material", "name": "6061铝合金", "category": "原材料",
         "specification": "T6热处理", "min_order_qty": 200},
        {"class": "Product", "name": "数控机床控制柜", "sku": "CNC-CTL-2025",
         "bom_version": "v3.2", "assembly_line": "3号产线"},
        {"class": "Product", "name": "伺服驱动器", "sku": "SERVO-DRV-2025",
         "bom_version": "v2.0", "assembly_line": "2号产线"},
        {"class": "ProductionLine", "name": "3号产线", "factory_location": "上海工厂",
         "capacity_per_day": 120, "status": "active"},
        {"class": "ProductionLine", "name": "2号产线", "factory_location": "上海工厂",
         "capacity_per_day": 80, "status": "active"},
        {"class": "LogisticsRoute", "name": "上海→深圳干线", "origin": "上海", "destination": "深圳",
         "transport_mode": "公路", "avg_transit_days": 3, "risk_score": 2},
        {"class": "LogisticsRoute", "name": "上海→武汉铁路", "origin": "上海", "destination": "武汉",
         "transport_mode": "铁路", "avg_transit_days": 2, "risk_score": 1},
        {"class": "Order", "order_id": "ORD-2025-0042", "customer": "比亚迪汽车",
         "status": "in_progress", "priority": "high", "delivery_deadline": "2025-07-25"},
        {"class": "Order", "order_id": "ORD-2025-0051", "customer": "特斯拉",
         "status": "pending", "priority": "high", "delivery_deadline": "2025-08-01"},
        {"class": "Order", "order_id": "ORD-2025-0038", "customer": "蔚来汽车",
         "status": "in_progress", "priority": "medium", "delivery_deadline": "2025-07-30"},
        {"class": "Warehouse", "name": "华东中心仓", "location": "苏州",
         "capacity": 100000, "inventory_level": 65000, "safety_stock_level": 20000},
        {"class": "Warehouse", "name": "华南前置仓", "location": "东莞",
         "capacity": 50000, "inventory_level": 28000, "safety_stock_level": 10000},
    ],
    "relations": [
        {"subject": "华东钢铁集团", "predicate": "supplies", "object": "304不锈钢板"},
        {"subject": "日立金属", "predicate": "supplies", "object": "SKD11模具钢"},
        {"subject": "宝钢股份", "predicate": "supplies", "object": "6061铝合金"},
        {"subject": "304不锈钢板", "predicate": "consumed_by", "object": "3号产线"},
        {"subject": "SKD11模具钢", "predicate": "consumed_by", "object": "2号产线"},
        {"subject": "3号产线", "predicate": "produces", "object": "数控机床控制柜"},
        {"subject": "2号产线", "predicate": "produces", "object": "伺服驱动器"},
        {"subject": "数控机床控制柜", "predicate": "fulfills", "object": "ORD-2025-0042"},
        {"subject": "伺服驱动器", "predicate": "fulfills", "object": "ORD-2025-0051"},
        {"subject": "ORD-2025-0042", "predicate": "ships_via", "object": "上海→深圳干线"},
        {"subject": "ORD-2025-0051", "predicate": "ships_via", "object": "上海→武汉铁路"},
        {"subject": "华东钢铁集团", "predicate": "stores_at", "object": "华东中心仓"},
        {"subject": "ORD-2025-0038", "predicate": "ships_via", "object": "上海→深圳干线"},
    ],
    "description": "供应链域种子数据：6类实体（Supplier/Material/Product/ProductionLine/LogisticsRoute/Order/Warehouse）+ 13条关系"
}

PROCUREMENT_SEEDS = {
    "entities": [
        {"class": "Supplier", "name": "浪潮信息", "register_capital": "10亿", "qualification_level": "A",
         "annual_revenue": "50亿", "employee_count": 5000},
        {"class": "Supplier", "name": "中科曙光", "register_capital": "8亿", "qualification_level": "A",
         "annual_revenue": "30亿", "employee_count": 3000},
        {"class": "Supplier", "name": "华为技术", "register_capital": "200亿", "qualification_level": "A",
         "annual_revenue": "7000亿", "employee_count": 200000},
        {"class": "PurchaseOrder", "po_id": "PO-2025-0089", "buyer": "某省政务云中心",
         "total_amount": 8500000, "status": "投标中"},
        {"class": "PurchaseOrder", "po_id": "PO-2025-0072", "buyer": "某市大数据局",
         "total_amount": 4200000, "status": "已中标"},
        {"class": "BidDocument", "bid_id": "BID-2025-0103", "project": "政务云平台扩容",
         "deadline": "2025-07-20", "status": "评审中"},
        {"class": "Invoice", "invoice_id": "INV-2025-0456", "amount": 1200000,
         "status": "已付款", "related_po": "PO-2025-0072"},
        {"class": "Contract", "contract_id": "CTR-2025-0033", "parties": ["浪潮信息", "某省政务云中心"],
         "amount": 8500000, "status": "草稿"},
    ],
    "relations": [
        {"subject": "浪潮信息", "predicate": "bids_for", "object": "PO-2025-0089"},
        {"subject": "中科曙光", "predicate": "bids_for", "object": "PO-2025-0089"},
        {"subject": "BID-2025-0103", "predicate": "related_to", "object": "PO-2025-0089"},
        {"subject": "INV-2025-0456", "predicate": "references", "object": "PO-2025-0072"},
        {"subject": "CTR-2025-0033", "predicate": "references", "object": "PO-2025-0089"},
        {"subject": "华为技术", "predicate": "bids_for", "object": "PO-2025-0072"},
        {"subject": "PO-2025-0072", "predicate": "awarded_to", "object": "华为技术"},
    ],
    "description": "采购域种子数据：5类实体(Supplier/PurchaseOrder/BidDocument/Invoice/Contract) + 7条关系"
}

SHIP_DESIGN_SEEDS = {
    "entities": [
        {"class": "Project", "name": "2025年度散货船项目", "vessel_type": "散货船",
         "deadweight": "82000", "owner": "中远海运"},
        {"class": "Discipline", "name": "船体结构", "code": "SD-HULL",
         "lead_engineer": "王工", "project": "2025年度散货船项目"},
        {"class": "Discipline", "name": "轮机系统", "code": "SD-MACH",
         "lead_engineer": "李工", "project": "2025年度散货船项目"},
        {"class": "Equipment", "name": "MAN B&W 6G70ME-C10", "type": "主机",
         "power_kw": 15800, "discipline": "轮机系统"},
        {"class": "Drawing", "drawing_no": "SD-HULL-100-001", "title": "船底结构图",
         "discipline": "船体结构", "status": "已送审", "revision": "B"},
        {"class": "ChangeRequest", "cr_id": "CR-2025-0037", "requested_by": "船东",
         "affected_disciplines": ["船体结构", "轮机系统"], "status": "评审中"},
        {"class": "OwnerComment", "comment_id": "OC-2025-0104", "drawing_ref": "SD-HULL-100-001",
         "comment": "船底纵骨间距调整为600mm", "status": "待回复"},
    ],
    "relations": [
        {"subject": "2025年度散货船项目", "predicate": "has_discipline", "object": "船体结构"},
        {"subject": "2025年度散货船项目", "predicate": "has_discipline", "object": "轮机系统"},
        {"subject": "MAN B&W 6G70ME-C10", "predicate": "installed_in", "object": "轮机系统"},
        {"subject": "SD-HULL-100-001", "predicate": "belongs_to", "object": "船体结构"},
        {"subject": "CR-2025-0037", "predicate": "affects", "object": "SD-HULL-100-001"},
        {"subject": "OC-2025-0104", "predicate": "references", "object": "SD-HULL-100-001"},
        {"subject": "OC-2025-0104", "predicate": "triggers", "object": "CR-2025-0037"},
    ],
    "description": "船舶设计域种子数据：7类实体(Project/Discipline/Equipment/Drawing/ChangeRequest/OwnerComment) + 7条关系"
}

DOMAINS = {
    "supply-chain": SUPPLY_CHAIN_SEEDS,
    "procurement-mvo": PROCUREMENT_SEEDS,
    "ship-design": SHIP_DESIGN_SEEDS,
}


def generate(domain_id: str) -> dict:
    if domain_id not in DOMAINS:
        print(f"  ⚠ No seed template for '{domain_id}', skipping")
        return None
    return DOMAINS[domain_id]


def save(domain_id: str, data: dict):
    path = os.path.join(SEED_DIR, f"{domain_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    entity_count = len(data["entities"])
    relation_count = len(data.get("relations", []))
    print(f"  {domain_id}: {entity_count} entities + {relation_count} relations → {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate domain seed data for Ontology Agent ingest")
    parser.add_argument("--domain", help="Single domain ID (e.g. supply-chain)")
    parser.add_argument("--all", action="store_true", help="Generate for all domains with templates")
    args = parser.parse_args()

    if args.all:
        target_domains = list(DOMAINS.keys())
    elif args.domain:
        target_domains = [args.domain]
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Generating seed data for {len(target_domains)} domain(s)...\n")
    for domain_id in target_domains:
        data = generate(domain_id)
        if data:
            save(domain_id, data)

    print(f"\nTo ingest: POST each file to /ontology/engine/process-and-write")
    print(f"Or run: python scripts/ingest_seed.py --domain <domain_id>")


if __name__ == "__main__":
    main()
