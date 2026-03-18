"""Tests for the discover module — parsing --help output and generating YAML."""

import textwrap

import yaml

from teukhos.discover import (
    DiscoveredArg,
    DiscoveredCommand,
    DiscoveryResult,
    _extract_description,
    generate_yaml,
    parse_commands,
    parse_options,
    parse_positional_args,
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
        yaml_str = generate_yaml(result, timeout=60)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["cli"]["timeout_seconds"] == 60

    def test_timeout_zero_is_included(self):
        """--timeout 0 should not be silently dropped."""
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result, timeout=0)
        config = yaml.safe_load(yaml_str)
        assert config["tools"][0]["cli"]["timeout_seconds"] == 0

    def test_timeout_none_excluded(self):
        result = self._make_result(tools=[
            DiscoveredCommand(name="cmd", subcommands=["cmd"]),
        ])
        yaml_str = generate_yaml(result, timeout=None)
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
