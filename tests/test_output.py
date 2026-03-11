"""Tests for output mapping."""

from mcpforge.config import OutputConfig, OutputType
from mcpforge.output import OutputMapper


def test_stdout_mapping():
    mapper = OutputMapper(OutputConfig(type=OutputType.stdout))
    result = mapper.map("hello world", "", 0)
    assert result == "hello world"


def test_stderr_mapping():
    mapper = OutputMapper(OutputConfig(type=OutputType.stderr))
    result = mapper.map("stdout", "stderr output", 0)
    assert result == "stderr output"


def test_json_field_simple():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="name"))
    result = mapper.map('{"name": "Alice", "age": 30}', "", 0)
    assert result == "Alice"


def test_json_field_nested():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="user.name"))
    result = mapper.map('{"user": {"name": "Bob"}}', "", 0)
    assert result == "Bob"


def test_json_field_array_index():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="items.0"))
    result = mapper.map('{"items": ["first", "second"]}', "", 0)
    assert result == "first"


def test_json_field_not_found():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="missing"))
    result = mapper.map('{"name": "test"}', "", 0)
    assert "not found" in result


def test_json_field_invalid_json():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="name"))
    result = mapper.map("not json at all", "", 0)
    assert "not valid JSON" in result


def test_json_field_returns_object():
    mapper = OutputMapper(OutputConfig(type=OutputType.json_field, field="data"))
    result = mapper.map('{"data": {"a": 1, "b": 2}}', "", 0)
    assert '"a": 1' in result


def test_exit_code_success():
    mapper = OutputMapper(
        OutputConfig(type=OutputType.exit_code, exit_codes={0: "All good", 1: "Failed"})
    )
    result = mapper.map("", "", 0)
    assert result == "All good"


def test_exit_code_failure():
    mapper = OutputMapper(
        OutputConfig(type=OutputType.exit_code, exit_codes={0: "OK", 1: "Bad"})
    )
    result = mapper.map("", "", 1)
    assert result == "Bad"


def test_exit_code_unknown():
    mapper = OutputMapper(OutputConfig(type=OutputType.exit_code))
    result = mapper.map("", "", 0)
    assert "Success" in result


def test_exit_code_unmapped():
    mapper = OutputMapper(OutputConfig(type=OutputType.exit_code, exit_codes={0: "OK"}))
    result = mapper.map("", "", 99)
    assert "exit code 99" in result
