"""Unit tests for server.py transport configuration (MCP_TRANSPORT/MCP_HOST/MCP_PORT)."""

import importlib
import sys

import pytest


@pytest.fixture
def reload_server(monkeypatch):
    """Reload server.py with a given env, return the module, then restore state."""
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")

    def _reload(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        if "server" in sys.modules:
            return importlib.reload(sys.modules["server"])
        return importlib.import_module("server")

    yield _reload

    sys.modules.pop("server", None)


def test_defaults_to_stdio(reload_server):
    server = reload_server()
    assert server.MCP_TRANSPORT == "stdio"
    assert server.MCP_HOST == "127.0.0.1"
    assert server.MCP_PORT == 8765
    assert server._transport_security is None


def test_streamable_http_env_overrides(reload_server):
    server = reload_server(
        MCP_TRANSPORT="streamable-http",
        MCP_HOST="0.0.0.0",
        MCP_PORT="9999",
    )
    assert server.MCP_TRANSPORT == "streamable-http"
    assert server.MCP_HOST == "0.0.0.0"
    assert server.MCP_PORT == 9999


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_no_transport_security_for_loopback_hosts(reload_server, host):
    server = reload_server(MCP_HOST=host)
    assert server._transport_security is None


def test_transport_security_enabled_for_non_loopback_host(reload_server):
    server = reload_server(MCP_HOST="0.0.0.0")
    settings = server._transport_security
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "localhost:*" in settings.allowed_hosts
    assert "http://127.0.0.1:*" in settings.allowed_origins
    assert "http://localhost:*" in settings.allowed_origins


def test_port_is_parsed_as_int(reload_server):
    server = reload_server(MCP_PORT="1234")
    assert server.MCP_PORT == 1234
    assert isinstance(server.MCP_PORT, int)


def test_allowed_hosts_extend_the_loopback_defaults(reload_server):
    # A container reached by its compose service name (gitlab-mcp:8765) sends that
    # as its Host header; without this it is rejected by DNS-rebinding protection.
    server = reload_server(MCP_HOST="0.0.0.0", MCP_ALLOWED_HOSTS="gitlab-mcp:*, other:8765")
    settings = server._transport_security
    assert settings.allowed_hosts == ["127.0.0.1:*", "localhost:*", "gitlab-mcp:*", "other:8765"]
    assert "http://gitlab-mcp:*" in settings.allowed_origins
    assert "http://other:8765" in settings.allowed_origins
