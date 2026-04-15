"""
pytest configuration and fixtures for aiPlat-core tests.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

# Add core to Python path
core_path = Path(__file__).parent.parent
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

# Also try adding the parent if needed
parent_path = core_path.parent
if str(parent_path) not in sys.path:
    sys.path.insert(0, str(parent_path))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def harness_config() -> Dict[str, Any]:
    """Create a basic harness configuration."""
    return {
        "enable_monitoring": True,
        "enable_observability": True,
        "enable_feedback_loops": False,
        "enable_memory": True,
        "enable_evolution": False,
        "monitoring_config": {},
        "memory_config": {"max_size": 100, "ttl": 3600},
        "feedback_config": {},
    }


@pytest.fixture
def memory_config() -> Dict[str, Any]:
    """Create a basic memory configuration."""
    return {
        "max_size": 100,
        "ttl": 3600,
    }


@pytest.fixture
def sample_memory_entry():
    """Create a sample memory entry for testing."""
    from harness.memory.base import MemoryEntry, MemoryType
    
    return MemoryEntry(
        id="test-entry-1",
        content="Test memory content",
        memory_type=MemoryType.CONVERSATION,
        metadata={"source": "test", "session_id": "test-session"},
        importance=0.7,
    )


@pytest.fixture
def sample_memory_entries():
    """Create multiple sample memory entries for testing."""
    from harness.memory.base import MemoryEntry, MemoryType
    
    return [
        MemoryEntry(
            id=f"test-entry-{i}",
            content=f"Test content {i}",
            memory_type=MemoryType.CONVERSATION,
            metadata={"index": i},
            importance=0.5 + (i * 0.1),
        )for i in range(5)
    ]