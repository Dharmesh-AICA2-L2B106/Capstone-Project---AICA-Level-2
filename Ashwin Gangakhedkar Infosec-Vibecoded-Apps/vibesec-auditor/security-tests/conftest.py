import pytest
import os
import requests
import logging

logger = logging.getLogger(__name__)

def pytest_configure(config):
    # Enforce Zero Production Impact Policy
    target_env = os.environ.get('VIBESEC_TARGET_URL', 'http://localhost:3000')
    if 'localhost' not in target_env and '127.0.0.1' not in target_env:
        allow_prod = os.environ.get('VIBESEC_ALLOW_PROD', 'false')
        if allow_prod.lower() != 'true':
            pytest.exit("WARNING: Non-local URL detected. Production testing is blocked by default to prevent data corruption. Set VIBESEC_ALLOW_PROD=true to override.")

@pytest.fixture(scope="session")
def base_url():
    return os.environ.get('VIBESEC_TARGET_URL', 'http://localhost:3000')

@pytest.fixture
def disposable_user_a(base_url):
    # Mock fixture to create and cleanup User A
    user = {"username": "vibesec_test_user_a", "role": "user"}
    yield user
    # Cleanup logic goes here
