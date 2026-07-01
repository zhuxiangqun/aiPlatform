"""E2E test configuration."""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end integration test")


@pytest.fixture(scope="session")
def base_url():
    return "http://localhost:8002"
