import pytest
from unittest.mock import MagicMock
from services.workflow import WorkflowEngine

def test_confirm_prd():
    db_mock = MagicMock()
    engine = WorkflowEngine(db_mock)
    result = engine.confirm_prd("test-id")
    assert result == "project not found"