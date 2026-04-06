"""Tests for LLM module — prompt building, response parsing."""
from axon.llm import build_prompt, _parse_response


def test_build_prompt_first_attempt():
    task = {"title": "Test", "description": "Desc", "eval_type": "exact_match",
            "direction": "maximize", "completion_threshold": 1.0}
    prompt = build_prompt(task, None, None, None)
    assert "Test" in prompt
    assert "first attempt" in prompt


def test_build_prompt_with_previous():
    task = {"title": "T", "description": "D", "eval_type": "numeric",
            "direction": "minimize", "completion_threshold": -0.01}
    prompt = build_prompt(task, "my answer", 0.5, 0.3)
    assert "my answer" in prompt
    assert "0.5" in prompt
    assert "lower is better" in prompt


def test_build_prompt_code_task():
    task = {"title": "T", "description": "D", "eval_type": "code_output",
            "direction": "maximize", "completion_threshold": -380}
    prompt = build_prompt(task, None, None, None)
    assert "Do NOT hardcode" in prompt


def test_build_prompt_with_error_feedback():
    task = {"title": "T", "description": "D", "eval_type": "code_output",
            "direction": "maximize", "completion_threshold": -380}
    feedback = {"error": "SyntaxError: invalid syntax", "details": {"stderr": "line 5"}, "score": None, "improved": False, "answer": "bad code"}
    prompt = build_prompt(task, None, None, None, feedback)
    assert "SyntaxError" in prompt
    assert "Fix the error" in prompt


def test_build_prompt_with_success_feedback():
    task = {"title": "T", "description": "D", "eval_type": "numeric",
            "direction": "maximize", "completion_threshold": -100}
    feedback = {"error": None, "details": {"stdout": "SIZE: 297 bytes"}, "score": -297, "improved": True, "answer": "code"}
    prompt = build_prompt(task, "code", -297, -200, feedback)
    assert "SIZE: 297" in prompt
    assert "improved" in prompt


def test_parse_response_with_tags():
    thinking, answer = _parse_response("<thinking>reason</thinking>\n<answer>42</answer>")
    assert thinking == "reason"
    assert answer == "42"


def test_parse_response_no_tags():
    thinking, answer = _parse_response("just plain text")
    assert answer == "just plain text"


def test_parse_response_strips_code_fences():
    thinking, answer = _parse_response("<answer>```python\nprint(1)\n```</answer>")
    assert "```" not in answer
    assert "print(1)" in answer


def test_parse_response_multiline():
    text = """<thinking>
I need to write a function.
Let me think step by step.
</thinking>
<answer>
def add(a, b):
    return a + b
</answer>"""
    thinking, answer = _parse_response(text)
    assert "step by step" in thinking
    assert "def add" in answer
