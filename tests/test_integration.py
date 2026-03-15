"""Integration tests — end-to-end testing of Teukhos server."""

from pathlib import Path

import pytest

from teukhos.config import load_config
from teukhos.engine import build_server


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.mark.asyncio
async def test_git_log_tool_e2e():
    """Full E2E: load config, build server, call git_log tool."""
    config = load_config(EXAMPLES_DIR / "git-tools.yaml")
    bundle = build_server(config)

    tool = await bundle.mcp.get_tool("git_log")
    result = await tool.fn(count=3)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    lines = result.strip().split("\n")
    assert len(lines) <= 3


@pytest.mark.asyncio
async def test_git_status_tool_e2e():
    """Full E2E: call git_status tool."""
    config = load_config(EXAMPLES_DIR / "git-tools.yaml")
    bundle = build_server(config)

    tool = await bundle.mcp.get_tool("git_status")
    result = await tool.fn()
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_git_branch_tool_e2e():
    """Full E2E: call git_branch tool."""
    config = load_config(EXAMPLES_DIR / "git-tools.yaml")
    bundle = build_server(config)

    tool = await bundle.mcp.get_tool("git_branch")
    result = await tool.fn()
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@pytest.mark.asyncio
async def test_invalid_args_error_handling():
    """Call a tool that will fail and verify error handling."""
    from teukhos.config import (
        ArgConfig,
        ArgType,
        CLIAdapterConfig,
        ForgeConfig,
        ForgeInfo,
        OutputConfig,
        ToolConfig,
    )

    config = ForgeConfig(
        forge=ForgeInfo(name="test-error"),
        tools=[
            ToolConfig(
                name="fail_tool",
                description="A tool that will fail",
                adapter="cli",
                cli=CLIAdapterConfig(command="ls"),
                args=[
                    ArgConfig(
                        name="path",
                        type=ArgType.string,
                        required=True,
                        positional=True,
                    )
                ],
                output=OutputConfig(),
            )
        ],
    )
    bundle = build_server(config)
    tool = await bundle.mcp.get_tool("fail_tool")
    result = await tool.fn(path="/nonexistent/path/that/does/not/exist")
    assert "Error" in result or "No such file" in result


@pytest.mark.asyncio
async def test_dev_tools_disk_usage():
    """E2E: call disk_usage from dev-tools."""
    config = load_config(EXAMPLES_DIR / "dev-tools.yaml")
    bundle = build_server(config)

    tool = await bundle.mcp.get_tool("disk_usage")
    result = await tool.fn(path="/tmp")
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@pytest.mark.asyncio
async def test_dev_tools_list_processes():
    """E2E: call list_processes from dev-tools."""
    config = load_config(EXAMPLES_DIR / "dev-tools.yaml")
    bundle = build_server(config)

    tool = await bundle.mcp.get_tool("list_processes")
    result = await tool.fn()
    assert isinstance(result, str)
    assert "PID" in result or "pid" in result.lower()


@pytest.mark.asyncio
async def test_exit_code_mapping_e2e():
    """E2E: verify exit code mapping works."""
    from teukhos.config import (
        ArgConfig,
        ArgType,
        CLIAdapterConfig,
        ForgeConfig,
        ForgeInfo,
        OutputConfig,
        OutputType,
        ToolConfig,
    )

    config = ForgeConfig(
        forge=ForgeInfo(name="test-exitcode"),
        tools=[
            ToolConfig(
                name="check_exit",
                description="Test exit codes",
                adapter="cli",
                cli=CLIAdapterConfig(command="bash", subcommand=["-c"]),
                args=[
                    ArgConfig(name="cmd", type=ArgType.string, positional=True, required=True)
                ],
                output=OutputConfig(
                    type=OutputType.exit_code,
                    exit_codes={0: "All good", 1: "Something failed"},
                ),
            )
        ],
    )
    bundle = build_server(config)
    tool = await bundle.mcp.get_tool("check_exit")
    result = await tool.fn(cmd="exit 0")
    assert result == "All good"
    result2 = await tool.fn(cmd="exit 1")
    assert result2 == "Something failed"


@pytest.mark.asyncio
async def test_all_example_configs_load():
    """Verify all example configs load and build servers successfully."""
    for yaml_file in EXAMPLES_DIR.glob("*.yaml"):
        config = load_config(yaml_file)
        bundle = build_server(config)
        assert bundle is not None
        tools = await bundle.mcp.list_tools()
        assert len(tools) > 0
