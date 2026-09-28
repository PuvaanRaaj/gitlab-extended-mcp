"""Protocol-level tests: tool annotations and error surfacing on mcp 2.x."""

import asyncio
import importlib
import sys

import httpx
import pytest
from mcp import Client


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.test")
    mod = importlib.reload(sys.modules["server"]) if "server" in sys.modules else importlib.import_module("server")
    yield mod
    sys.modules.pop("server", None)


def _call(server, name, args):
    async def go():
        async with Client(server.mcp) as client:
            return await client.call_tool(name, args)
    return asyncio.run(go())


def _mock_gitlab(monkeypatch, server, handler):
    real_client = httpx.Client
    monkeypatch.setattr(server.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


def test_every_tool_has_annotations(server):
    tools = asyncio.run(server.mcp.list_tools())
    assert len(tools) == 49
    for t in tools:
        assert t.annotations is not None, t.name
        assert t.annotations.open_world_hint is True, t.name


def test_read_and_destructive_hints(server):
    tools = {t.name: t.annotations for t in asyncio.run(server.mcp.list_tools())}
    assert tools["get_issue"].read_only_hint is True
    assert tools["create_issue"].read_only_hint is False
    assert tools["create_issue"].destructive_hint is False
    assert tools["cancel_job"].destructive_hint is True
    assert tools["resolve_mr_discussion"].idempotent_hint is True


def test_gitlab_error_text_reaches_model(server, monkeypatch):
    _mock_gitlab(monkeypatch, server, lambda req: httpx.Response(404, text='{"message":"404 Project Not Found"}'))
    result = _call(server, "get_issue", {"id": "a/b", "issue_iid": 1})
    assert result.is_error is True
    text = result.content[0].text
    assert "GitLab 404" in text
    assert "Project Not Found" in text


def test_conflicts_409_still_handled(server, monkeypatch):
    _mock_gitlab(monkeypatch, server, lambda req: httpx.Response(409, text="conflict"))
    result = _call(
        server, "get_merge_request_conflicts", {"project_id": "a/b", "merge_request_iid": 1})
    assert result.is_error is False
    assert "no conflicts" in result.content[0].text


def test_missing_args_is_error_result(server):
    result = _call(server, "get_workitem_notes", {})
    assert result.is_error is True
    assert "required" in result.content[0].text
