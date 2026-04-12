"""Tests for config module."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from axon.config import load_config, save_config, get_token, DEFAULT_CONFIG, resolve_cli_timeout


def test_load_default_config(tmp_path):
    with patch("axon.config.CONFIG_FILE", tmp_path / "nonexistent.json"):
        config = load_config()
        assert config["server_url"] == "http://localhost:8000"
        assert config["auth_token"] == ""
        assert config["api_keys"] == {}


def test_save_and_load(tmp_path):
    config_file = tmp_path / "config.json"
    with patch("axon.config.CONFIG_FILE", config_file), \
         patch("axon.config.CONFIG_DIR", tmp_path):
        save_config({"auth_token": "test-jwt", "default_model": "openai/gpt-4o"})
        config = load_config()
        assert config["auth_token"] == "test-jwt"
        assert config["default_model"] == "openai/gpt-4o"
        assert config["server_url"] == "http://localhost:8000"  # default preserved


def test_save_api_keys_merge(tmp_path):
    config_file = tmp_path / "config.json"
    with patch("axon.config.CONFIG_FILE", config_file), \
         patch("axon.config.CONFIG_DIR", tmp_path):
        save_config({"api_keys": {"anthropic": "sk-ant-123"}})
        save_config({"api_keys": {"openai": "sk-proj-456"}})
        config = load_config()
        assert config["api_keys"]["anthropic"] == "sk-ant-123"
        assert config["api_keys"]["openai"] == "sk-proj-456"


def test_get_token_empty(tmp_path):
    with patch("axon.config.CONFIG_FILE", tmp_path / "nonexistent.json"):
        token = get_token()
        assert token == ""


def test_load_corrupt_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("not json {{{")
    with patch("axon.config.CONFIG_FILE", config_file):
        config = load_config()
        assert config == {**DEFAULT_CONFIG}


def test_resolve_cli_timeout_positive():
    assert resolve_cli_timeout({"cli_timeout": 900}) == 900


def test_resolve_cli_timeout_disabled_by_zero():
    assert resolve_cli_timeout({"cli_timeout": 0}) is None


def test_resolve_cli_timeout_disabled_by_null():
    assert resolve_cli_timeout({"cli_timeout": None}) is None


def test_resolve_cli_timeout_invalid_uses_default():
    assert resolve_cli_timeout({"cli_timeout": "bad"}) == 600
