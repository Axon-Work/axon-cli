"""Tests for axon.backends — factory, litellm, claude-cli, codex-cli."""
import json
from unittest.mock import patch, MagicMock

import pytest

from axon.backends import create_backend
from axon.backends.claude_cli import _parse_response as claude_parse
from axon.backends.codex_cli import _parse_response as codex_parse


# --- Factory ---

def test_create_backend_litellm():
    b = create_backend("litellm", {"default_model": "test/model"})
    assert b.name == "litellm"
    assert b.display_name() == "test/model"


def test_create_backend_claude_cli():
    b = create_backend("claude-cli", {})
    assert b.name == "claude-cli"
    assert "claude-cli" in b.display_name()


def test_create_backend_codex_cli():
    b = create_backend("codex-cli", {})
    assert b.name == "codex-cli"
    assert "codex-cli" in b.display_name()


def test_create_backend_unknown():
    with pytest.raises(ValueError, match="Unknown backend"):
        create_backend("nonexistent", {})


# --- LiteLLM Backend ---

@patch("axon.llm.call_llm")
def test_litellm_backend_call(mock_call):
    mock_call.return_value = ("thinking text", "answer text", {"total_tokens": 100, "cost": 0.01})
    b = create_backend("litellm", {"default_model": "test/m"})
    result = b.call("prompt", {"eval_type": "code_output"})
    assert result["thinking"] == "thinking text"
    assert result["answer"] == "answer text"
    assert result["usage"]["total_tokens"] == 100
    mock_call.assert_called_once_with("prompt", "test/m", "")


# --- Claude CLI Backend ---

def test_claude_parse_v2_array():
    """Test parsing Claude CLI v2.1+ JSON array format."""
    data = json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "result", "result": json.dumps({"thinking": "I think...", "answer": "42"})},
    ])
    result = claude_parse(data)
    assert result["thinking"] == "I think..."
    assert result["answer"] == "42"


def test_claude_parse_v2_array_with_dict_result():
    """Test parsing when result is already a dict."""
    data = json.dumps([
        {"type": "system"},
        {"type": "result", "result": {"thinking": "reasoning", "answer": "hello"}},
    ])
    result = claude_parse(data)
    assert result["thinking"] == "reasoning"
    assert result["answer"] == "hello"


def test_claude_parse_v2_array_with_usage():
    """Claude CLI is subscription-based — usage values should be None."""
    data = json.dumps([
        {"type": "system"},
        {"type": "result", "result": {"thinking": "", "answer": "ok"},
         "total_cost_usd": 0.05,
         "usage": {"input_tokens": 50, "output_tokens": 30}},
    ])
    result = claude_parse(data)
    assert result["usage"]["billing_mode"] == "subscription"
    assert result["usage"]["tokens"] is None
    assert result["usage"]["cost_usd"] is None


def test_claude_parse_single_object():
    """Test parsing a single JSON object (older format)."""
    data = json.dumps({"thinking": "reason", "answer": "result"})
    result = claude_parse(data)
    assert result["thinking"] == "reason"
    assert result["answer"] == "result"


def test_claude_parse_plain_text_result():
    """Test fallback when result is plain text."""
    data = json.dumps([
        {"type": "result", "result": "just a string answer"},
    ])
    result = claude_parse(data)
    assert result["answer"] == "just a string answer"
    assert result["thinking"] == ""


def test_claude_parse_empty():
    with pytest.raises(RuntimeError, match="empty output"):
        claude_parse("")


def test_claude_parse_no_result_block():
    data = json.dumps([{"type": "system"}])
    with pytest.raises(RuntimeError, match="No result block"):
        claude_parse(data)


@patch("subprocess.Popen")
def test_claude_cli_call_builds_correct_command(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = (
        json.dumps([{"type": "result", "result": {"thinking": "t", "answer": "a"}}]),
        "",
    )
    proc.returncode = 0
    mock_popen.return_value = proc

    b = create_backend("claude-cli", {"cli_timeout": 120, "claude_cli_model": "opus"})
    result = b.call("test prompt", {"eval_type": "code_output"})

    assert result["answer"] == "a"
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--allowedTools" in cmd
    tools_idx = cmd.index("--allowedTools") + 1
    assert "Bash" in cmd[tools_idx]
    system_idx = cmd.index("--system-prompt") + 1
    assert "raw executable Python code" in cmd[system_idx]
    assert "Do NOT wrap it in <answer> tags" in cmd[system_idx]
    assert "--model" in cmd
    assert "opus" in cmd


@patch("subprocess.Popen")
def test_claude_cli_timeout(mock_popen):
    import subprocess as sp
    proc = MagicMock()
    proc.communicate.side_effect = sp.TimeoutExpired(cmd="claude", timeout=5)
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    mock_popen.return_value = proc

    b = create_backend("claude-cli", {"cli_timeout": 5})
    with pytest.raises(TimeoutError, match="timed out"):
        b.call("prompt", {})


@patch("subprocess.Popen")
def test_claude_cli_nonzero_exit(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = ("", "error msg")
    proc.returncode = 1
    mock_popen.return_value = proc

    b = create_backend("claude-cli", {})
    with pytest.raises(RuntimeError, match="exited with code 1"):
        b.call("prompt", {})


@patch("subprocess.Popen")
def test_claude_cli_no_hard_timeout(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = (
        json.dumps([{"type": "result", "result": {"thinking": "t", "answer": "a"}}]),
        "",
    )
    proc.returncode = 0
    mock_popen.return_value = proc

    b = create_backend("claude-cli", {"cli_timeout": 0})
    result = b.call("prompt", {"eval_type": "code_output"})

    assert result["answer"] == "a"
    assert proc.communicate.call_args.kwargs["timeout"] is None


# --- Codex CLI Backend ---

def test_codex_parse_json():
    data = json.dumps({"thinking": "thought", "answer": "result"})
    result = codex_parse(data)
    assert result["thinking"] == "thought"
    assert result["answer"] == "result"


def test_codex_parse_embedded_json():
    data = 'Some preamble text\n{"thinking": "hmm", "answer": "42"}\nSome trailing text'
    result = codex_parse(data)
    assert result["answer"] == "42"


def test_codex_parse_plain_text_fallback():
    result = codex_parse("Just a plain answer with no JSON")
    assert result["answer"] == "Just a plain answer with no JSON"
    assert result["thinking"] == ""


def test_codex_parse_empty():
    with pytest.raises(RuntimeError, match="empty output"):
        codex_parse("")


@patch("subprocess.Popen")
def test_codex_cli_call(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = (
        json.dumps({"thinking": "t", "answer": "a"}),
        "",
    )
    proc.returncode = 0
    mock_popen.return_value = proc

    b = create_backend("codex-cli", {"codex_cli_model": "o3"})
    result = b.call("test prompt", {})

    assert result["answer"] == "a"
    assert result["usage"]["billing_mode"] == "subscription"
    assert result["usage"]["tokens"] is None
    assert result["usage"]["cost_usd"] is None
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "codex"
    assert cmd[1] == "exec"
    assert "--model" in cmd
    assert "o3" in cmd
    wrapped_prompt = proc.communicate.call_args.kwargs["input"]
    assert 'answer" field must contain ONLY raw executable Python code' in wrapped_prompt
    assert 'Do NOT include XML tags' in wrapped_prompt


@patch("subprocess.Popen")
def test_codex_cli_timeout(mock_popen):
    import subprocess as sp
    proc = MagicMock()
    proc.communicate.side_effect = sp.TimeoutExpired(cmd="codex", timeout=5)
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    mock_popen.return_value = proc

    b = create_backend("codex-cli", {"cli_timeout": 5})
    with pytest.raises(TimeoutError, match="timed out"):
        b.call("prompt", {})


@patch("subprocess.Popen")
def test_codex_cli_no_hard_timeout(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = (
        json.dumps({"thinking": "t", "answer": "a"}),
        "",
    )
    proc.returncode = 0
    mock_popen.return_value = proc

    b = create_backend("codex-cli", {"cli_timeout": 0})
    result = b.call("prompt", {})

    assert result["answer"] == "a"
    assert proc.communicate.call_args.kwargs["timeout"] is None


# --- Tool selection ---

@patch("subprocess.Popen")
def test_claude_cli_tool_selection_by_eval_type(mock_popen):
    proc = MagicMock()
    proc.communicate.return_value = (
        json.dumps([{"type": "result", "result": {"thinking": "", "answer": ""}}]),
        "",
    )
    proc.returncode = 0
    mock_popen.return_value = proc

    b = create_backend("claude-cli", {})

    # code_output → includes Bash
    b.call("p", {"eval_type": "code_output"})
    cmd = mock_popen.call_args[0][0]
    tools_idx = cmd.index("--allowedTools") + 1
    assert "Bash" in cmd[tools_idx]
    assert "Write" in cmd[tools_idx]

    # llm_judge → includes WebSearch
    b.call("p", {"eval_type": "llm_judge"})
    cmd = mock_popen.call_args[0][0]
    tools_idx = cmd.index("--allowedTools") + 1
    assert "WebSearch" in cmd[tools_idx]
    assert "Bash" not in cmd[tools_idx]

    # unknown → default tools
    b.call("p", {"eval_type": "other"})
    cmd = mock_popen.call_args[0][0]
    tools_idx = cmd.index("--allowedTools") + 1
    assert "WebSearch" in cmd[tools_idx]
    assert "Bash" not in cmd[tools_idx]


# --- Claude CLI answer tag parsing ---

def test_claude_parse_xml_answer_tags():
    """Test that <answer> XML tags are correctly extracted from result text."""
    data = json.dumps([
        {"type": "result", "result": "<answer>\ndef solve(x):\n    return x * 2\n</answer>"},
    ])
    result = claude_parse(data)
    assert result["answer"] == "def solve(x):\n    return x * 2"
    assert result["thinking"] == ""


def test_claude_parse_mixed_content_with_answer_tag():
    """Test that <answer> tags are extracted even when surrounded by prose."""
    data = json.dumps([
        {"type": "result", "result": (
            "I've tested the code and it works correctly. Here's my solution:\n\n"
            "<answer>\nimport sys\n\ndef main():\n    print('hello')\n\nmain()\n</answer>\n\n"
            "This solution handles all edge cases."
        )},
    ])
    result = claude_parse(data)
    assert result["answer"] == "import sys\n\ndef main():\n    print('hello')\n\nmain()"
    assert result["thinking"] == ""
