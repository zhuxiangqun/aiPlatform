"""E2E test configuration."""
import os

import httpx
import pytest

# Defaults match docker-compose.test.yml edge tokens.
CORE_API_TOKEN = os.getenv("AIPLAT_CORE_API_TOKEN", "e2e-core-token")
PLATFORM_API_TOKEN = os.getenv("AIPLAT_PLATFORM_API_TOKEN", "e2e-platform-token")


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end integration test")


@pytest.fixture(scope="session")
def base_url():
    return "http://localhost:8002"


def _e2e_auth_headers(url: str) -> dict[str, str]:
    """Pick the edge token for the service under test."""
    if ":8003" in url or "/api/platform/" in url:
        return {
            "X-AIPLAT-PLATFORM-TOKEN": PLATFORM_API_TOKEN,
            "X-AIPLAT-API-KEY": PLATFORM_API_TOKEN,
        }
    if ":8002" in url or "/api/core/" in url:
        return {
            "X-AIPLAT-CORE-TOKEN": CORE_API_TOKEN,
            "X-AIPLAT-API-KEY": CORE_API_TOKEN,
        }
    return {}


def _attach_edge_tokens(request: httpx.Request) -> None:
    for key, value in _e2e_auth_headers(str(request.url)).items():
        request.headers[key] = value


@pytest.fixture(scope="module")
def client():
    """httpx client with edge tokens for core/platform binds."""
    return httpx.Client(
        timeout=httpx.Timeout(30.0),
        event_hooks={"request": [_attach_edge_tokens]},
    )
