import os
import pytest
from runtime_adapters.config import Settings, ConfigurationError

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_ENABLED", raising=False)
    assert Settings.from_env().enabled is False

def test_enabled_requires_model_and_family(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://x")
    with pytest.raises(ConfigurationError, match="LLM_MODEL_CREATION"):
        Settings.from_env()

def test_family_must_be_explicit(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("LLM_MODEL_CREATION", "example-model")
    with pytest.raises(ConfigurationError, match="LLM_FAMILY_CREATION"):
        Settings.from_env()
