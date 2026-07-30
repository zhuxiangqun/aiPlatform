"""Real-time context — bridge DataSource APIs to RunContext fields.

Phase 10.3: queries configured DataSources (``~/.aiplat/datasources/*.yaml``)
that have a ``mapping.run_context`` section, and maps API responses to
RunContext fields (situation, priority, constraints).

When no DataSource is configured, returns None gracefully — caller falls
back to GraphIndex topology.

Moved from materials_chat.py Phase 1 refactoring.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("aiplat.realtime_context")


def fetch_realtime_context(entity_name: str, domain_id: str) -> Optional[dict]:
    """Fetch real-time operational data from external DataSource APIs.

    Config format (``~/.aiplat/datasources/equipment-realtime.yaml``)::

        name: equipment-realtime
        type: api
        connection:
          base_url: "http://mes.internal/api/v1"
          endpoint: "/equipment/{entity}/status"
          method: GET
          auth:
            type: bearer
            token_env: MES_API_TOKEN
        mapping:
          run_context:
            situation_template: "{status_desc}: {value}{unit}"
            priority_path: "alert_level"
            priority_mapping:
              critical: "critical"
              warning: "elevated"
              normal: "normal"
            constraints_path: "available_resources"
    """
    try:
        from core.harness.ontology_engine.data_source import DataSourceRegistry, DataSourceConfig

        DataSourceRegistry.load_from_dir()
        for source_id, config in DataSourceRegistry._configs.items():
            mapping = config.mapping
            if not isinstance(mapping, dict) or "run_context" not in mapping:
                continue
            rc_map = mapping["run_context"]
            if not isinstance(rc_map, dict):
                continue

            ds = DataSourceRegistry.get(source_id)
            if not ds:
                continue

            endpoint_tpl = config.connection.get("endpoint", "")
            endpoint = endpoint_tpl.replace("{entity}", entity_name)
            records = ds.fetch_all(limit=1)

            if not records:
                continue

            record = records[0]

            ctx: dict = {"entity": entity_name, "entity_type": "", "situation": "", "priority": "", "constraints": []}

            target_class = mapping.get("target_class", "")
            if target_class:
                ctx["entity_type"] = target_class

            sit_tpl = rc_map.get("situation_template", "")
            if sit_tpl:
                try:
                    ctx["situation"] = sit_tpl.format(**record)
                except (KeyError, ValueError):
                    pass  # noqa: cleanup-best-effort

            prio_path = rc_map.get("priority_path", "")
            if prio_path:
                raw_prio = record.get(prio_path, "") or ""
                prio_map = rc_map.get("priority_mapping", {})
                if isinstance(prio_map, dict) and raw_prio in prio_map:
                    ctx["priority"] = prio_map[raw_prio]
                else:
                    ctx["priority"] = str(raw_prio).lower()

            const_path = rc_map.get("constraints_path", "")
            if const_path:
                constraints = record.get(const_path, [])
                if isinstance(constraints, list):
                    ctx["constraints"] = [str(c) for c in constraints[:10]]
                elif isinstance(constraints, str):
                    ctx["constraints"] = [constraints]

            return ctx

        return None
    except Exception:
        return None

