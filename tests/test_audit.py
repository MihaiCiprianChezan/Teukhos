"""Tests for the tool-call audit log."""

import json
import sys

import pytest
from fastmcp import Client

from teukhos.config import ArgConfig, ArgType, CLIAdapterConfig, ForgeConfig, ServerConfig, ToolConfig
from teukhos.engine import build_server


def _server(tmp_path, args, script="import sys; print(sys.argv[1:]); sys.exit(int(sys.argv[-1]))"):
    log = tmp_path / "logs" / "audit.jsonl"
    config = ForgeConfig(
        server=ServerConfig(audit_log=str(log)),
        tools=[ToolConfig(
            name="t",
            cli=CLIAdapterConfig(command=sys.executable, subcommand=["-c", script]),
            args=args,
        )],
    )
    return Client(build_server(config).mcp), log


def _entries(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_audit_records_each_call(tmp_path):
    client, log = _server(tmp_path, [
        ArgConfig(name="label", flag="--label"),
        ArgConfig(name="code", type=ArgType.integer, positional=True, required=True),
    ])
    async with client:
        await client.call_tool("t", {"label": "a", "code": 0})
        await client.call_tool("t", {"code": 3}, raise_on_error=False)
    first, second = _entries(log)
    assert first["tool"] == "t" and first["args"] == {"label": "a", "code": 0}
    assert first["ok"] is True and first["exit_code"] == 0 and first["user"] is None
    assert isinstance(first["duration_ms"], int) and first["time"].endswith("+00:00")
    assert second["ok"] is False and second["exit_code"] == 3


@pytest.mark.asyncio
async def test_audit_masks_secrets_and_records_rejections(tmp_path):
    client, log = _server(tmp_path, [
        ArgConfig(name="token", flag="--token", secret=True, default="sk-SECRET-DEFAULT"),
        ArgConfig(name="pin", flag="--pin", secret=True),
        ArgConfig(name="path", positional=True),
        ArgConfig(name="code", type=ArgType.integer, positional=True, required=True),
    ])
    async with client:
        await client.call_tool("t", {"pin": "1234", "code": 0})
        await client.call_tool("t", {"path": "--evil", "code": 0}, raise_on_error=False)
    ok, rejected = _entries(log)
    assert ok["args"] == {"pin": "[REDACTED]", "code": 0}
    assert "sk-SECRET-DEFAULT" not in log.read_text(encoding="utf-8")
    assert rejected["ok"] is False and rejected["exit_code"] is None
    assert "must not start with '-'" in rejected["error"]


def test_audit_log_path_checked_at_startup(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    config = ForgeConfig(server=ServerConfig(audit_log=str(blocker / "audit.jsonl")))
    with pytest.raises(OSError):
        build_server(config)
