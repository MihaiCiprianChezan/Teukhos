"""Tests for the discover module — parsing --help output and generating YAML."""

import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest
import yaml

from teukhos.discover import (
    DiscoveredArg,
    DiscoveredCommand,
    DiscoveryResult,
    _extract_description,
    discover_binary,
    generate_yaml,
    parse_commands,
    parse_options,
    parse_positional_args,
    run_help,
)


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_explicit_description_section(self):
        text = textwrap.dedent("""\
            Usage: my-tool [OPTIONS]

            Description:
              A tool that does great things.

            Options:
              --help  Show help
        """)
        assert _extract_description(text) == "A tool that does great things."

    def test_fallback_skips_usage_line(self):
        text = textwrap.dedent("""\
            Usage: my-tool [OPTIONS]

            A tool that does great things.

            Options:
              --help  Show help
        """)
        assert _extract_description(text) == "A tool that does great things."

    def test_skips_commands_header(self):
        text = textwrap.dedent("""\
            Commands:
              init  Initialize
        """)
        # Should not pick "Commands:" or indented command entries as description
        assert _extract_description(text) == ""

    def test_stops_at_multiword_commands_header(self):
        text = textwrap.dedent("""\
            CORE COMMANDS
              pr          Work with pull requests
              issue       Work with issues
        """)
        assert _extract_description(text) == ""

    def test_empty_text(self):
        assert _extract_description("") == ""

    def test_only_headers(self):
        text = textwrap.dedent("""\
            Usage: tool [OPTIONS]
            Options:
            Arguments:
        """)
        assert _extract_description(text) == ""


# ---------------------------------------------------------------------------
# parse_commands
# ---------------------------------------------------------------------------

class TestParseCommands:
    def test_basic_commands_section(self):
        text = textwrap.dedent("""\
            Usage: tool [OPTIONS] COMMAND [ARGS]...

            Commands:
              init        Initialize the repository
              status      Show the current status
        """)
        result = parse_commands(text)
        assert result == [("init", "Initialize the repository"), ("status", "Show the current status")]

    def test_gh_style_sections(self):
        """gh CLI uses CORE COMMANDS and ADDITIONAL COMMANDS sections."""
        text = textwrap.dedent("""\
            CORE COMMANDS
              pr          Work with pull requests
              issue       Work with issues

            ADDITIONAL COMMANDS
              alias       Create command shortcuts
              api         Make authenticated API requests
        """)
        result = parse_commands(text)
        names = [c[0] for c in result]
        assert names == ["pr", "issue", "alias", "api"]

    def test_deduplication(self):
        """Same command in multiple sections should not appear twice."""
        text = textwrap.dedent("""\
            CORE COMMANDS
              pr          Work with pull requests

            ADDITIONAL COMMANDS
              pr          Work with pull requests (alias)
        """)
        result = parse_commands(text)
        assert len(result) == 1
        assert result[0][0] == "pr"

    def test_colon_style_commands(self):
        text = textwrap.dedent("""\
            Commands:
              init:  Initialize the repository
              build: Build the project
        """)
        result = parse_commands(text)
        names = [c[0] for c in result]
        assert names == ["init", "build"]

    def test_stops_at_options_section(self):
        text = textwrap.dedent("""\
            Commands:
              init        Initialize

            Options:
              --help      Show help
        """)
        result = parse_commands(text)
        assert len(result) == 1
        assert result[0][0] == "init"

    def test_no_commands_section(self):
        text = textwrap.dedent("""\
            Usage: tool [OPTIONS]

            Options:
              --help  Show help
        """)
        assert parse_commands(text) == []


# ---------------------------------------------------------------------------
# parse_options
# ---------------------------------------------------------------------------

class TestParseOptions:
    def test_gnu_style(self):
        text = textwrap.dedent("""\
            Options:
              -f, --force           Force the operation
              --count <INT>         Number of items
              -q, --quiet           Suppress output
        """)
        opts = parse_options(text)
        assert len(opts) == 3
        assert opts[0].flag == "--force"
        assert opts[0].short_flag == "-f"
        assert opts[0].is_boolean is True
        assert opts[1].flag == "--count"
        assert opts[1].arg_type == "string"  # <INT> isn't in the known hint list
        assert opts[2].flag == "--quiet"

    def test_skips_help_and_version(self):
        text = textwrap.dedent("""\
            Options:
              -h, --help            Show help
              --version             Show version
              -f, --force           Force it
        """)
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].flag == "--force"

    def test_required_flag(self):
        text = "  --name <NAME>         The name (REQUIRED)\n"
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].required is True
        assert "(REQUIRED)" not in opts[0].description

    def test_default_value_extraction(self):
        text = "  --port <PORT>         Server port [default: 8080]\n"
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].default == "8080"
        assert opts[0].arg_type == "integer"
        assert "[default:" not in opts[0].description

    def test_azure_cli_style(self):
        text = "  --resource-group -g : The resource group name.\n"
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].flag == "--resource-group"
        assert opts[0].short_flag == "-g"
        assert opts[0].description == "The resource group name."

    def test_deduplication(self):
        text = textwrap.dedent("""\
              --name <VALUE>         The name
              --name <VALUE>         Duplicate entry
        """)
        opts = parse_options(text)
        assert len(opts) == 1

    def test_reserved_keyword_gets_suffix(self):
        text = "  --from <VALUE>         Source address\n"
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].name == "from_value"
        assert opts[0].flag == "--from"

    def test_integer_hint_types(self):
        text = textwrap.dedent("""\
              --limit <limit>         Max results
              --port <port>           Server port
              --count <count>         Number of items
        """)
        opts = parse_options(text)
        for opt in opts:
            assert opt.arg_type == "integer", f"{opt.name} should be integer"


# ---------------------------------------------------------------------------
# parse_positional_args
# ---------------------------------------------------------------------------

class TestParsePositionalArgs:
    def test_basic_positionals(self):
        text = textwrap.dedent("""\
            Arguments:
              <file>          Input file path
              <output-dir>    Output directory
        """)
        result = parse_positional_args(text)
        assert len(result) == 2
        assert result[0].name == "file"
        assert result[0].required is True
        assert result[0].positional is True
        assert result[1].name == "output_dir"

    def test_no_arguments_section(self):
        text = textwrap.dedent("""\
            Options:
              --help  Show help
        """)
        assert parse_positional_args(text) == []

    def test_stops_at_next_section(self):
        text = textwrap.dedent("""\
            Arguments:
              <file>          Input file

            Options:
              --help  Show help
        """)
        result = parse_positional_args(text)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# generate_yaml
# ---------------------------------------------------------------------------

class TestGenerateYaml:
    def _make_result(self, **kwargs):
        return DiscoveryResult(binary="my-tool", binary_name="my-tool", **kwargs)

    def test_basic_generation(self):
        result = self._make_result(
            description="A test tool",
            tools=[
                DiscoveredCommand(
                    name="init",
                    description="Initialize",
                    subcommands=["init"],
                    args=[
                        DiscoveredArg(name="force", flag="--force", is_boolean=True, arg_type="boolean"),
                    ],
                ),
            ],
        )
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)

        assert config["forge"]["name"] == "my-tool"
        assert config["forge"]["description"] == "A test tool"
        assert len(config["tools"]) == 1
        assert config["tools"][0]["name"] == "init"
        assert config["tools"][0]["cli"]["command"] == "my-tool"
        assert config["tools"][0]["cli"]["subcommand"] == ["init"]
        assert config["tools"][0]["args"][0]["name"] == "force"
        assert config["tools"][0]["args"][0]["type"] == "boolean"

    def test_timeout_included_when_set(self):
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result, exec_timeout=60)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["cli"]["timeout_seconds"] == 60

    def test_timeout_zero_is_included(self):
        """--exec-timeout 0 should not be silently dropped."""
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result, exec_timeout=0)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["cli"]["timeout_seconds"] == 0

    def test_timeout_none_excluded(self):
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result, exec_timeout=None)
        config = yaml.safe_load(yaml_str)
        assert "timeout_seconds" not in config["tools"][0]["cli"]

    def test_positional_args_come_first(self):
        result = self._make_result(tools=[
            DiscoveredCommand(
                name="run",
                subcommands=["run"],
                positional_args=[
                    DiscoveredArg(name="file", positional=True, required=True),
                ],
                args=[
                    DiscoveredArg(name="verbose", flag="--verbose", is_boolean=True, arg_type="boolean"),
                ],
            ),
        ])
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)
        args = config["tools"][0]["args"]
        assert args[0]["name"] == "file"
        assert args[0]["positional"] is True
        assert args[1]["name"] == "verbose"

    def test_default_integer_coercion(self):
        result = self._make_result(tools=[
            DiscoveredCommand(
                name="serve",
                subcommands=["serve"],
                args=[
                    DiscoveredArg(name="port", flag="--port", arg_type="integer", default="8080"),
                ],
            ),
        ])
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["args"][0]["default"] == 8080


# ---------------------------------------------------------------------------
# CLI wiring: --timeout vs --exec-timeout (real CLI integration tests)
# ---------------------------------------------------------------------------

class TestCliTimeoutWiring:
    """Invoke the real Typer CLI and verify --timeout goes to discovery,
    --exec-timeout goes to generated YAML."""

    @staticmethod
    def _fake_result():
        return DiscoveryResult(
            binary="my-tool", binary_name="my-tool", description="test",
            tools=[DiscoveredCommand(name="cmd", subcommands=["cmd"])],
        )

    def test_timeout_passed_to_discover_binary(self, monkeypatch, tmp_path):
        """--timeout value reaches discover_binary, not generate_yaml."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        captured = {}

        def fake_discover(binary, *, max_depth=2, filter_prefix=None, timeout=15):
            captured["timeout"] = timeout
            return self._fake_result()

        monkeypatch.setattr("teukhos.discover.discover_binary", fake_discover)
        monkeypatch.setattr("teukhos.discover.generate_yaml", lambda r, **kw: "forge: {}\ntools: []\n")

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--timeout", "30", "--dry-run"])
        assert result.exit_code == 0
        assert captured["timeout"] == 30

    def test_exec_timeout_passed_to_generate_yaml(self, monkeypatch, tmp_path):
        """--exec-timeout value reaches generate_yaml as exec_timeout."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        captured = {}

        def fake_discover(binary, *, max_depth=2, filter_prefix=None, timeout=15):
            return self._fake_result()

        def fake_generate(result, *, exec_timeout=None):
            captured["exec_timeout"] = exec_timeout
            return "forge: {}\ntools: []\n"

        monkeypatch.setattr("teukhos.discover.discover_binary", fake_discover)
        monkeypatch.setattr("teukhos.discover.generate_yaml", fake_generate)

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--exec-timeout", "120", "--dry-run"])
        assert result.exit_code == 0
        assert captured["exec_timeout"] == 120

    def test_timeout_does_not_leak_into_yaml(self, monkeypatch, tmp_path):
        """--timeout alone should not set exec_timeout in generate_yaml."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        captured = {}

        def fake_discover(binary, *, max_depth=2, filter_prefix=None, timeout=15):
            return self._fake_result()

        def fake_generate(result, *, exec_timeout=None):
            captured["exec_timeout"] = exec_timeout
            return "forge: {}\ntools: []\n"

        monkeypatch.setattr("teukhos.discover.discover_binary", fake_discover)
        monkeypatch.setattr("teukhos.discover.generate_yaml", fake_generate)

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--timeout", "30", "--dry-run"])
        assert result.exit_code == 0
        assert captured["exec_timeout"] is None

    def test_default_timeout_is_15(self, monkeypatch, tmp_path):
        """Omitting --timeout should pass 15 to discover_binary."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        _SENTINEL = object()
        captured = {}

        def fake_discover(binary, *, max_depth=2, filter_prefix=None, timeout=_SENTINEL):
            captured["timeout"] = timeout
            return self._fake_result()

        monkeypatch.setattr("teukhos.discover.discover_binary", fake_discover)
        monkeypatch.setattr("teukhos.discover.generate_yaml", lambda r, **kw: "forge: {}\ntools: []\n")

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--dry-run"])
        assert result.exit_code == 0
        assert captured["timeout"] == 15

    def test_cli_filter_passed_to_discover(self, monkeypatch):
        """--filter splits into a list and reaches discover_binary as filter_prefix."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        captured = {}

        def fake_discover(binary, *, max_depth=2, filter_prefix=None, timeout=15):
            captured["filter_prefix"] = filter_prefix
            return self._fake_result()

        monkeypatch.setattr("teukhos.discover.discover_binary", fake_discover)
        monkeypatch.setattr("teukhos.discover.generate_yaml", lambda r, **kw: "forge: {}\ntools: []\n")

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--filter", "vm list", "--dry-run"])
        assert result.exit_code == 0
        assert captured["filter_prefix"] == ["vm", "list"]

    def test_cli_output_writes_file(self, monkeypatch, tmp_path):
        """--output writes YAML to the specified file."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        monkeypatch.setattr("teukhos.discover.discover_binary", lambda *a, **kw: self._fake_result())
        monkeypatch.setattr("teukhos.discover.generate_yaml", lambda r, **kw: "forge: {name: test}\ntools: []\n")

        out_file = tmp_path / "out.yaml"
        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--output", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        assert "forge:" in out_file.read_text()

    def test_cli_discover_binary_error_exits_1(self, monkeypatch):
        """When discover_binary raises, CLI prints error and exits 1."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        def exploding_discover(*a, **kw):
            raise RuntimeError("No --help output")

        monkeypatch.setattr("teukhos.discover.discover_binary", exploding_discover)

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "bad-binary", "--dry-run"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_cli_no_tools_exits_1(self, monkeypatch):
        """When discover finds zero tools, CLI warns and exits 1."""
        from typer.testing import CliRunner
        from teukhos.cli import app

        empty_result = DiscoveryResult(binary="x", binary_name="x", tools=[])
        monkeypatch.setattr("teukhos.discover.discover_binary", lambda *a, **kw: empty_result)

        runner = CliRunner()
        result = runner.invoke(app, ["discover", "my-tool", "--dry-run"])
        assert result.exit_code == 1
        assert "No tools discovered" in result.output


# ---------------------------------------------------------------------------
# run_help
# ---------------------------------------------------------------------------

class TestRunHelp:
    def test_real_binary_returns_output(self):
        """run_help with python --version should return output."""
        output = run_help(sys.executable, ["--version".replace("--help", "")], timeout=10)
        # python --help (the function appends --help) returns usage info
        result = run_help(sys.executable, [], timeout=10)
        assert result is not None
        assert len(result) > 0

    def test_nonexistent_binary_returns_none(self):
        result = run_help("nonexistent_binary_xyz_12345")
        assert result is None

    def test_timeout_returns_none(self):
        """A command that exceeds timeout should return None."""
        # Use a Python sleep that takes longer than the timeout
        result = run_help(
            sys.executable,
            ["-c", "import time; time.sleep(10)"],
            timeout=1,
        )
        # run_help appends --help, so the actual command is:
        # python -c "import time; time.sleep(10)" --help
        # This will either timeout or fail — either way, we handle it
        # Let's use a more reliable approach: mock subprocess.run to raise
        with patch("teukhos.discover.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
            result = run_help("any-binary", timeout=1)
        assert result is None

    def test_prefers_stdout_over_stderr(self):
        """When both stdout and stderr have content, stdout wins."""
        fake_result = subprocess.CompletedProcess(
            args=["test"], returncode=0, stdout="stdout content", stderr="stderr content"
        )
        with patch("teukhos.discover.subprocess.run", return_value=fake_result):
            result = run_help("test-binary")
        assert result == "stdout content"

    def test_falls_back_to_stderr(self):
        """When stdout is empty, stderr is used."""
        fake_result = subprocess.CompletedProcess(
            args=["test"], returncode=0, stdout="", stderr="stderr content"
        )
        with patch("teukhos.discover.subprocess.run", return_value=fake_result):
            result = run_help("test-binary")
        assert result == "stderr content"

    def test_empty_output_returns_none(self):
        fake_result = subprocess.CompletedProcess(
            args=["test"], returncode=0, stdout="", stderr=""
        )
        with patch("teukhos.discover.subprocess.run", return_value=fake_result):
            result = run_help("test-binary")
        assert result is None


# ---------------------------------------------------------------------------
# discover_binary
# ---------------------------------------------------------------------------

class TestDiscoverBinary:
    SIMPLE_HELP = textwrap.dedent("""\
        Usage: my-tool [OPTIONS] COMMAND

        A simple test tool.

        Commands:
          init        Initialize the project
          build       Build the project

        Options:
          --help  Show help
    """)

    LEAF_HELP = textwrap.dedent("""\
        Usage: my-tool init [OPTIONS]

        Initialize the project.

        Options:
          -f, --force           Force reinit
          --help                Show help
    """)

    BUILD_HELP = textwrap.dedent("""\
        Usage: my-tool build [OPTIONS]

        Build the project.

        Options:
          --target <TARGET>     Build target
          --help                Show help
    """)

    def _mock_run_help(self, binary, args=None, timeout=15):
        """Return canned help text based on the args."""
        if args is None or args == []:
            return self.SIMPLE_HELP
        if args == ["init"]:
            return self.LEAF_HELP
        if args == ["build"]:
            return self.BUILD_HELP
        return None

    def test_discovers_leaf_commands(self):
        """Recursion finds leaf commands and extracts their args."""
        with patch("teukhos.discover.run_help", side_effect=self._mock_run_help):
            result = discover_binary("my-tool", max_depth=2)

        assert result.binary_name == "my-tool"
        assert result.description == "A simple test tool."
        assert len(result.tools) == 2
        names = {t.name for t in result.tools}
        assert names == {"init", "build"}

        # Check init has --force arg
        init_tool = next(t for t in result.tools if t.name == "init")
        assert any(a.flag == "--force" for a in init_tool.args)

        # Check build has --target arg
        build_tool = next(t for t in result.tools if t.name == "build")
        assert any(a.flag == "--target" for a in build_tool.args)

    def test_no_help_output_raises_runtime_error(self):
        with patch("teukhos.discover.run_help", return_value=None):
            with pytest.raises(RuntimeError, match="Could not get --help output"):
                discover_binary("broken-tool")

    def test_binary_with_no_subcommands(self):
        """A binary whose --help has no Commands section is treated as a single tool."""
        leaf_only = textwrap.dedent("""\
            Usage: simple-tool [OPTIONS]

            A tool with no subcommands.

            Options:
              --verbose           Enable verbose output
              --help              Show help
        """)
        with patch("teukhos.discover.run_help", return_value=leaf_only):
            result = discover_binary("simple-tool")

        assert len(result.tools) == 1
        assert result.tools[0].name == "simple_tool"
        assert result.tools[0].description == "A tool with no subcommands."

    def test_max_depth_registers_as_leaves(self):
        """At max_depth, commands with subcommands are registered as leaves."""
        with patch("teukhos.discover.run_help", side_effect=self._mock_run_help):
            result = discover_binary("my-tool", max_depth=0)

        # At depth 0, init and build have no further subcommands in their help,
        # but they are at max_depth so treated as leaf registrations
        assert len(result.tools) == 2

    def test_filter_prefix(self):
        """filter_prefix starts discovery from a subtree."""
        calls = []

        def tracking_run_help(binary, args=None, timeout=15):
            calls.append(args)
            if args == ["init"] or args is None:
                return self.LEAF_HELP
            return None

        with patch("teukhos.discover.run_help", side_effect=tracking_run_help):
            result = discover_binary("my-tool", filter_prefix=["init"])

        # First call should be with ["init"] (the filter prefix)
        assert calls[0] == ["init"]

    def test_timeout_forwarded_to_run_help(self):
        """The timeout parameter is passed through to every run_help call."""
        timeouts = []

        def tracking_run_help(binary, args=None, timeout=15):
            timeouts.append(timeout)
            if args is None or args == []:
                return self.SIMPLE_HELP
            return self.LEAF_HELP

        with patch("teukhos.discover.run_help", side_effect=tracking_run_help):
            discover_binary("my-tool", timeout=42)

        assert all(t == 42 for t in timeouts)

    def test_skips_subcommand_when_help_fails(self):
        """If a subcommand's --help fails, it's skipped without crashing."""
        def selective_help(binary, args=None, timeout=15):
            if args is None or args == []:
                return self.SIMPLE_HELP
            if args == ["init"]:
                return self.LEAF_HELP
            return None  # build --help fails

        with patch("teukhos.discover.run_help", side_effect=selective_help):
            result = discover_binary("my-tool")

        assert len(result.tools) == 1
        assert result.tools[0].name == "init"

    def test_binary_name_sanitization(self):
        """Spaces and casing in binary path are sanitized in binary_name."""
        with patch("teukhos.discover.run_help", return_value="A simple tool.\n"):
            result = discover_binary("C:\\Program Files\\My Tool.exe")

        assert result.binary_name == "my-tool"


# ---------------------------------------------------------------------------
# generate_yaml — additional edge cases
# ---------------------------------------------------------------------------

class TestGenerateYamlEdgeCases:
    def _make_result(self, **kwargs):
        return DiscoveryResult(binary="my-tool", binary_name="my-tool", **kwargs)

    def test_tool_with_no_args_omits_args_key(self):
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)
        assert "args" not in config["tools"][0]

    def test_non_numeric_default_on_integer_arg(self):
        """An integer-typed arg with a non-numeric default keeps the string default."""
        result = self._make_result(tools=[
            DiscoveredCommand(
                name="cmd", subcommands=["cmd"],
                args=[DiscoveredArg(name="size", flag="--size", arg_type="integer", default="auto")],
            ),
        ])
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["args"][0]["default"] == "auto"

    def test_multiple_tools_in_result(self):
        result = self._make_result(
            description="multi",
            tools=[
                DiscoveredCommand(name="a", subcommands=["a"]),
                DiscoveredCommand(name="b", subcommands=["b"]),
                DiscoveredCommand(name="c", subcommands=["c"]),
            ],
        )
        yaml_str = generate_yaml(result)
        config = yaml.safe_load(yaml_str)
        assert len(config["tools"]) == 3
        assert [t["name"] for t in config["tools"]] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# parse_options — additional edge cases
# ---------------------------------------------------------------------------

class TestParseOptionsEdgeCases:
    def test_duration_hint_is_integer(self):
        text = "  --wait <duration>         How long to wait\n"
        opts = parse_options(text)
        assert len(opts) == 1
        assert opts[0].arg_type == "integer"
