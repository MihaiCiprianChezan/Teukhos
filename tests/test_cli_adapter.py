"""Tests for the CLI adapter."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from teukhos.adapters.cli import CLIAdapter
from teukhos.config import ArgConfig, ArgType, CLIAdapterConfig


@pytest.fixture
def echo_adapter():
    cli_config = CLIAdapterConfig(
        command=sys.executable,
        subcommand=["-c", "import sys; print(sys.argv[1])"],
    )
    args = [
        ArgConfig(name="message", type=ArgType.string, required=True, positional=True),
    ]
    return CLIAdapter(cli_config, args)


@pytest.fixture
def git_log_adapter():
    import pathlib as _pl
    _repo = str(_pl.Path(__file__).parent.parent)
    cli_config = CLIAdapterConfig(command="git", subcommand=["log", "--oneline"], working_dir=_repo)
    args = [
        ArgConfig(name="count", type=ArgType.integer, flag="-n", default=5),
    ]
    return CLIAdapter(cli_config, args)


@pytest.mark.asyncio
async def test_echo_basic(echo_adapter):
    result = await echo_adapter.execute(message="hello world")
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello world"


@pytest.mark.asyncio
async def test_echo_empty(echo_adapter):
    result = await echo_adapter.execute(message="")
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_git_log(git_log_adapter):
    result = await git_log_adapter.execute(count=5)
    if result.exit_code == 128:
        import pytest as _p; _p.skip("No git history in this environment")
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.strip().split("\n") if ln]
    assert len(lines) <= 5


@pytest.mark.asyncio
async def test_timeout():
    cli_config = CLIAdapterConfig(
        command=sys.executable,
        subcommand=["-c", "import time; time.sleep(10)"],
        timeout_seconds=1,
    )
    adapter = CLIAdapter(cli_config, [])
    result = await adapter.execute()
    assert result.exit_code == -1
    assert "timed out" in result.stderr


@pytest.mark.asyncio
async def test_nonexistent_command():
    cli_config = CLIAdapterConfig(command="nonexistent_binary_xyz")
    adapter = CLIAdapter(cli_config, [])
    warning = adapter.check_binary()
    assert warning is not None
    assert "not found" in warning


@pytest.mark.asyncio
async def test_exit_code():
    cli_config = CLIAdapterConfig(
        command=sys.executable,
        subcommand=["-c", "import sys; sys.exit(int(sys.argv[1]))"],
    )
    args = [ArgConfig(name="code", type=ArgType.string, positional=True, required=True)]
    adapter = CLIAdapter(cli_config, args)
    result = await adapter.execute(code="42")
    assert result.exit_code == 42


@pytest.mark.asyncio
async def test_boolean_flag():
    cli_config = CLIAdapterConfig(command="git", subcommand=["branch"])
    args = [ArgConfig(name="all", type=ArgType.boolean, flag="--all")]
    adapter = CLIAdapter(cli_config, args)
    cmd = adapter._build_command(all=True)
    assert "--all" in cmd
    cmd2 = adapter._build_command(all=False)
    assert "--all" not in cmd2


@pytest.mark.asyncio
async def test_json_output():
    cli_config = CLIAdapterConfig(
        command=sys.executable,
        subcommand=["-c", "import sys; print(sys.argv[1])"],
    )
    args = [ArgConfig(name="data", type=ArgType.string, positional=True, required=True)]
    adapter = CLIAdapter(cli_config, args)
    result = await adapter.execute(data='{"name": "test", "count": 42}')
    assert result.exit_code == 0
    assert "test" in result.stdout


def _argv_adapter(*args: ArgConfig, **cli) -> CLIAdapter:
    """Adapter whose command prints the argv it received."""
    cli_config = CLIAdapterConfig(
        command=sys.executable, subcommand=["-c", "import sys; print(sys.argv[1:])"], **cli
    )
    return CLIAdapter(cli_config, list(args))


@pytest.mark.asyncio
async def test_positional_leading_dash_rejected(echo_adapter):
    """An agent value like '--output=/tmp/x' must not reach the binary as an option."""
    result = await echo_adapter.execute(message="--output=/tmp/x")
    assert result.exit_code == -1
    assert "must not start with '-'" in result.stderr


@pytest.mark.asyncio
async def test_bare_arg_leading_dash_rejected():
    result = await _argv_adapter(ArgConfig(name="target")).execute(target="-rf")
    assert result.exit_code == -1
    assert "must not start with '-'" in result.stderr


@pytest.mark.asyncio
async def test_leading_dash_allowed_for_flag_values_enum_and_default():
    adapter = _argv_adapter(
        ArgConfig(name="pattern", flag="-e"),
        ArgConfig(name="mode", positional=True, enum=["-v", "-q"]),
        ArgConfig(name="src", positional=True, default="-"),
    )
    result = await adapter.execute(pattern="-x", mode="-v")
    assert result.exit_code == 0
    assert "['-e', '-x', '-v', '-']" in result.stdout


@pytest.mark.asyncio
async def test_nul_byte_in_argument_returns_error(echo_adapter):
    result = await echo_adapter.execute(message="a\x00b")
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_env_extends_parent_environment():
    cli_config = CLIAdapterConfig(
        command=sys.executable,
        subcommand=["-c", "import os; print('PATH' in os.environ, os.environ['TEUKHOS_TEST_VAR'])"],
        env={"TEUKHOS_TEST_VAR": "x"},
    )
    result = await CLIAdapter(cli_config, []).execute()
    assert result.stdout.strip() == "True x"


@pytest.mark.asyncio
async def test_missing_working_dir_reported(tmp_path):
    cli_config = CLIAdapterConfig(
        command=sys.executable, subcommand=["-c", "pass"], working_dir=str(tmp_path / "missing")
    )
    result = await CLIAdapter(cli_config, []).execute()
    assert result.exit_code == -1
    assert "working_dir" in result.stderr
    assert "not found" not in result.stderr


@pytest.mark.asyncio
async def test_working_dir_expands_home():
    cli_config = CLIAdapterConfig(
        command=sys.executable, subcommand=["-c", "import os; print(os.getcwd())"], working_dir="~"
    )
    result = await CLIAdapter(cli_config, []).execute()
    assert os.path.samefile(result.stdout.strip(), Path.home())


@pytest.mark.asyncio
async def test_non_executable_command_reported(tmp_path):
    not_a_binary = tmp_path / "notes.txt"
    not_a_binary.write_text("hello")
    result = await CLIAdapter(CLIAdapterConfig(command=str(not_a_binary)), []).execute()
    assert result.exit_code == -1
    assert "Failed to run" in result.stderr


@pytest.mark.asyncio
async def test_output_truncated_at_max_output_bytes():
    cli_config = CLIAdapterConfig(
        command=sys.executable, subcommand=["-c", "print('x' * 5000)"], max_output_bytes=1000
    )
    result = await CLIAdapter(cli_config, []).execute()
    assert result.exit_code == 0
    kept, marker = result.stdout.split("\n[output truncated: ")
    assert kept == "x" * 1000
    assert marker.endswith("showing first 1000]")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch-file handling")
@pytest.mark.asyncio
async def test_batch_shim_resolved_and_metacharacters_rejected(tmp_path, monkeypatch):
    (tmp_path / "teukhos_shim.cmd").write_text("@echo off\r\necho shim-got %*\r\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    marker = tmp_path / "pwned.txt"
    arg = ArgConfig(name="text", positional=True)

    # Bare name resolves to the .cmd shim (CreateProcess alone would only try .exe)
    shim = CLIAdapter(CLIAdapterConfig(command="teukhos_shim"), [arg])
    ok = await shim.execute(text="hello world")
    assert ok.exit_code == 0
    assert "shim-got" in ok.stdout

    # cmd.exe would run '&echo.>pwned.txt' as a second command
    for command in ["teukhos_shim", str(tmp_path / "teukhos_shim.cmd."), str(tmp_path / "teukhos_shim.CMD ")]:
        bad = await CLIAdapter(CLIAdapterConfig(command=command), [arg]).execute(text=f"x&echo.>{marker}")
        assert bad.exit_code == -1, command
        assert "batch file" in bad.stderr
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows current-directory search")
def test_bare_command_not_resolved_from_current_directory(tmp_path):
    """A planted <name>.exe in the server's cwd must not shadow PATH (binary planting)."""
    shutil.copy(Path(os.environ["SystemRoot"]) / "System32" / "whoami.exe", tmp_path / "teukhos_probe.exe")
    env = {k: v for k, v in os.environ.items() if k.upper() != "NODEFAULTCURRENTDIRECTORYINEXEPATH"}
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)  # this checkout, not an installed teukhos
    code = (
        "import anyio; from teukhos.adapters.cli import CLIAdapter; "
        "from teukhos.config import CLIAdapterConfig; "
        "r = anyio.run(CLIAdapter(CLIAdapterConfig(command='teukhos_probe'), []).execute); "
        "print(r.exit_code, r.stderr)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert "not found" in out.stdout, out.stdout + out.stderr


@pytest.mark.asyncio
async def test_negative_number_positional_rejected():
    adapter = _argv_adapter(ArgConfig(name="n", type=ArgType.number, positional=True))
    result = await adapter.execute(n=float("-inf"))
    assert result.exit_code == -1
    assert "must not start with '-'" in result.stderr


@pytest.mark.asyncio
async def test_secret_redacted_before_truncation():
    """A cut at max_output_bytes must not expose the start of a secret."""
    secret = "sk-ABCDEFGHIJKLMNOP"
    for pad in range(0, 25):
        cli_config = CLIAdapterConfig(
            command=sys.executable,
            subcommand=["-c", f"import sys; sys.stdout.write('x' * {pad} + sys.argv[-1] + 'y' * 200)"],
            max_output_bytes=20,
        )
        adapter = CLIAdapter(cli_config, [ArgConfig(name="tok", positional=True, secret=True, default=secret)])
        result = await adapter.execute()
        assert result.truncated
        assert "sk-A" not in result.stdout, pad


@pytest.mark.asyncio
async def test_overlapping_secrets_fully_redacted():
    adapter = _argv_adapter(
        ArgConfig(name="user", flag="--user", secret=True, default="admin"),
        ArgConfig(name="pw", flag="--pw", secret=True, default="admin-Hunter2!"),
    )
    result = await adapter.execute()
    assert "Hunter2" not in result.stdout
    assert result.stdout.count("[REDACTED]") == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch-file handling")
@pytest.mark.asyncio
async def test_batch_argument_separators_rejected(tmp_path):
    shim = tmp_path / "teukhos_sep.cmd"
    shim.write_text("@echo off\r\necho 1=[%1] 2=[%2]\r\n")
    adapter = CLIAdapter(CLIAdapterConfig(command=str(shim)), [ArgConfig(name="text", positional=True)])
    assert (await adapter.execute(text="plain value")).exit_code == 0
    for value in ["x,y", "x;y", "x=y", "x\x0cy", "x　y"]:
        result = await adapter.execute(text=value)
        assert result.exit_code == -1, repr(value)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command lookup")
@pytest.mark.asyncio
async def test_batch_shim_is_only_a_fallback(tmp_path, monkeypatch):
    """A .bat earlier on PATH must not shadow the .exe that CreateProcess finds."""
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "teukhos_dual.bat").write_text("@echo off\r\necho BAT-SHIM\r\n")
    shutil.copy(Path(os.environ["SystemRoot"]) / "System32" / "whoami.exe", second / "teukhos_dual.exe")
    monkeypatch.setenv("PATH", f"{first}{os.pathsep}{second}{os.pathsep}{os.environ['PATH']}")
    result = await CLIAdapter(CLIAdapterConfig(command="teukhos_dual"), []).execute()
    assert result.exit_code == 0
    assert "BAT-SHIM" not in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows best-fit conversion")
@pytest.mark.asyncio
async def test_windows_best_fit_look_alikes_rejected(echo_adapter):
    for value in ["－－output=x", "−x", "a ＂ b"]:
        result = await echo_adapter.execute(message=value)
        assert result.exit_code == -1, repr(value)


@pytest.mark.skipif(sys.platform != "win32", reason="MSYS runtime")
def test_msys_noglob_set():
    import teukhos.adapters.cli  # noqa: F401  (sets the variables on import)
    assert "noglob" in os.environ["MSYS"]
    assert "noglob" in os.environ["CYGWIN"]


@pytest.mark.asyncio
async def test_secret_default_from_environment(monkeypatch):
    """default: env:VAR keeps the credential out of the YAML; it is resolved per call and redacted."""
    adapter = _argv_adapter(ArgConfig(name="token", flag="--token", secret=True, default="env:TK_TEST_TOKEN"))
    monkeypatch.delenv("TK_TEST_TOKEN", raising=False)
    missing = await adapter.execute()
    assert missing.exit_code == -1 and "TK_TEST_TOKEN is not set" in missing.stderr
    monkeypatch.setenv("TK_TEST_TOKEN", "sk-from-env")
    result = await adapter.execute()
    assert result.exit_code == 0
    assert "sk-from-env" not in result.stdout and "[REDACTED]" in result.stdout
