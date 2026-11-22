"""N07/N22 deepen：platform ingest/watch/vault → wiki_auto_update 身份透传；非 certified / 非伪造 cron 角色。"""
from __future__ import annotations

import inspect
from pathlib import Path


def test_auto_wiki_update_signature_has_actor():
    from api.rest import routes as routes_mod

    sig = inspect.signature(routes_mod._auto_wiki_update)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    src = inspect.getsource(routes_mod._auto_wiki_update)
    assert "actor_role=actor_role" in src
    assert "wiki_auto_update(" in src


def test_documents_ingest_wires_identity_to_auto_wiki():
    routes_path = Path(__file__).resolve().parents[1] / "api" / "rest" / "routes.py"
    src = routes_path.read_text(encoding="utf-8")
    assert "actor_role=str(identity.actor_role" in src
    assert "_auto_wiki_update(" in src
    assert "actor_scopes=list(identity.scopes" in src


def test_watch_directory_signature_and_wiki_call_wires_actor():
    from kb import service as kb_svc

    sig = inspect.signature(kb_svc.watch_directory)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    src = inspect.getsource(kb_svc.watch_directory)
    assert "actor_role=_actor_role" in src
    assert "actor_scopes=_actor_scopes" in src
    assert "wiki_auto_update(" in src


def test_kb_watch_route_passes_identity():
    from api.rest import routes as routes_mod

    src = inspect.getsource(routes_mod.kb_watch_directory)
    assert "actor_role=str(identity.actor_role" in src
    assert "actor_scopes=list(identity.scopes" in src
    assert "watch_directory(" in src


def test_vault_to_wiki_signature_wires_actor():
    from kb import service as kb_svc

    sig = inspect.signature(kb_svc.vault_to_wiki)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    src = inspect.getsource(kb_svc.vault_to_wiki)
    assert "actor_role=actor_role" in src
    assert "wiki_auto_update(" in src


def test_vault_send_to_wiki_resolves_identity():
    from api.rest import routes as routes_mod

    src = inspect.getsource(routes_mod.vault_send_to_wiki)
    assert "_resolve_identity" in src
    assert "actor_role=role" in src
    assert "actor_scopes=scopes" in src


def test_vault_start_indexer_wires_actor():
    from kb import service as kb_svc

    sig = inspect.signature(kb_svc.vault_start_indexer)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    src = inspect.getsource(kb_svc.vault_start_indexer)
    assert "actor_role=_actor_role" in src
    assert "vault_to_wiki(" in src


def test_vault_index_start_route_passes_identity():
    from api.rest import routes as routes_mod

    src = inspect.getsource(routes_mod.vault_index_start)
    assert "_resolve_identity" in src
    assert "actor_role=str(identity.actor_role" in src
    assert "vault_start_indexer(" in src
