"""LLM integration — call Anthropic/OpenAI/Ollama via litellm."""
import re
import os

from axon.config import load_config


def build_prompt(task, my_best_answer, my_best_score, platform_best_score, last_feedback=None, community_subs=None, my_past_subs=None):
    direction_text = "higher is better" if task.get("direction") == "maximize" else "lower is better"
    is_code = task.get("eval_type") == "code_output"

    prompt = f"# Task: {task['title']}\n\n## Description\n{task['description']}\n\n"
    prompt += f"## Evaluation\nScored using: {task['eval_type']}\nDirection: {task['direction']} ({direction_text})\n"
    prompt += f"Completion threshold: {task['completion_threshold']}\n"
    prompt += f"Platform best: {platform_best_score if platform_best_score is not None else 'None (no submissions yet)'}\n"

    if community_subs:
        prompt += "\n## Community Submissions (top scores from other miners)\n"
        for i, sub in enumerate(community_subs[:3], 1):
            score = sub.get("score")
            score_str = f"{score:.4f}" if score is not None else "N/A"
            prompt += f"  #{i}  score: {score_str}\n"

    if my_past_subs:
        recent_subs = my_past_subs[-10:]
        prompt += "\n## Your Past Submissions (DO NOT repeat these answers)\n"
        for i, sub in enumerate(recent_subs, 1):
            score = sub.get("score")
            eval_status = sub.get("eval_status", "unknown")
            error = sub.get("eval_error")
            if error:
                prompt += f"  #{i}  score=error   status={eval_status}  error={error[:120]}\n"
            elif score is not None:
                prompt += f"  #{i}  score={score:.4f}  status={eval_status}\n"
            else:
                prompt += f"  #{i}  score=N/A     status={eval_status}\n"
            answer_text = sub.get("answer")
            if answer_text:
                preview = answer_text[:500]
                if len(answer_text) > 500:
                    preview += "... (truncated)"
                prompt += f"    Answer: {preview}\n"
        prompt += "\nAvoid submitting answers similar to the ones above. Try a different approach.\n"

    if my_best_answer is not None and my_best_score is not None:
        prompt += f"\n## Your Current Best\nScore: {my_best_score}\nAnswer:\n{my_best_answer}\n"

    if last_feedback:
        prompt += "\n## Last Round Feedback\n"
        if last_feedback.get("error"):
            prompt += f"Status: ERROR\nError: {last_feedback['error']}\n"
            if last_feedback.get("details", {}).get("stderr"):
                prompt += f"Stderr:\n{str(last_feedback['details']['stderr'])[:500]}\n"
            prompt += f"\nYour submission that caused this error:\n{last_feedback.get('answer', '')}\n"
            prompt += "\nFix the error and try again.\n"
        else:
            status = "improved (but not yet completed)" if last_feedback.get("improved") else "no improvement"
            prompt += f"Score: {last_feedback.get('score')}\nStatus: {status}\n"
            if last_feedback.get("details", {}).get("stdout"):
                prompt += f"Eval output:\n{str(last_feedback['details']['stdout'])[:300]}\n"
            prompt += "\nAnalyze the eval output and your score. Find ways to improve.\n"
    elif not my_best_answer:
        prompt += "\nThis is your first attempt. Think carefully.\n"

    if is_code:
        prompt += (
            "\n## CRITICAL RULES\n"
            "1. Do NOT hardcode test data. Input comes via function parameters.\n"
            "2. Functions must work with ANY input.\n"
            "3. The evaluator writes your submission directly to solution.py and executes it.\n"
            "4. Inside <answer>, include ONLY raw executable Python code.\n"
            "5. Do NOT include XML tags, prose, or markdown fences inside the submitted code.\n\n"
            "## Code Restrictions (enforced by sandbox)\n"
            "- Banned imports: os, subprocess, sys, shutil, signal, ctypes, socket, http, "
            "urllib, requests, httpx, importlib, pickle, shelve, marshal, multiprocessing, "
            "threading, concurrent, pathlib\n"
            "- Banned calls: eval(), exec(), compile(), __import__()\n"
            "- Max code size: 5MB\n"
            "- Code that violates these restrictions will be rejected with score 0.\n\n"
        )

    prompt += f"## OUTPUT FORMAT\n<thinking>your reasoning</thinking>\n<answer>{'RAW EXECUTABLE PYTHON CODE ONLY' if is_code else 'your answer'}</answer>\n"
    return prompt


def build_agent_prompt(task, my_best_answer, my_best_score, platform_best_score, last_feedback=None, community_subs=None, my_past_subs=None):
    """Build prompt for CLI agent backends (claude-cli, codex-cli).

    Unlike build_prompt(), this omits XML output format instructions (CLI backends
    use --json-schema or embedded JSON format) and adds tool usage guidance.
    """
    direction_text = "higher is better" if task.get("direction") == "maximize" else "lower is better"
    is_code = task.get("eval_type") == "code_output"
    eval_type = task.get("eval_type", "")

    prompt = f"# Task: {task['title']}\n\n## Description\n{task['description']}\n\n"
    prompt += f"## Evaluation\nScored using: {eval_type}\nDirection: {task['direction']} ({direction_text})\n"
    prompt += f"Completion threshold: {task['completion_threshold']}\n"
    prompt += f"Platform best: {platform_best_score if platform_best_score is not None else 'None (no submissions yet)'}\n"

    if community_subs:
        prompt += "\n## Community Submissions (top scores from other miners)\n"
        for i, sub in enumerate(community_subs[:3], 1):
            score = sub.get("score")
            score_str = f"{score:.4f}" if score is not None else "N/A"
            prompt += f"  #{i}  score: {score_str}\n"

    if my_past_subs:
        recent_subs = my_past_subs[-10:]
        prompt += "\n## Your Past Submissions (DO NOT repeat these answers)\n"
        for i, sub in enumerate(recent_subs, 1):
            score = sub.get("score")
            eval_status = sub.get("eval_status", "unknown")
            error = sub.get("eval_error")
            if error:
                prompt += f"  #{i}  score=error   status={eval_status}  error={error[:120]}\n"
            elif score is not None:
                prompt += f"  #{i}  score={score:.4f}  status={eval_status}\n"
            else:
                prompt += f"  #{i}  score=N/A     status={eval_status}\n"
            answer_text = sub.get("answer")
            if answer_text:
                preview = answer_text[:500]
                if len(answer_text) > 500:
                    preview += "... (truncated)"
                prompt += f"    Answer: {preview}\n"
        prompt += "\nAvoid submitting answers similar to the ones above. Try a different approach.\n"

    if my_best_answer is not None and my_best_score is not None:
        prompt += f"\n## Your Current Best\nScore: {my_best_score}\nAnswer:\n{my_best_answer}\n"

    if last_feedback:
        prompt += "\n## Last Round Feedback\n"
        if last_feedback.get("error"):
            prompt += f"Status: ERROR\nError: {last_feedback['error']}\n"
            if last_feedback.get("details", {}).get("stderr"):
                prompt += f"Stderr:\n{str(last_feedback['details']['stderr'])[:500]}\n"
            prompt += f"\nYour submission that caused this error:\n{last_feedback.get('answer', '')}\n"
            prompt += "\nFix the error and try again.\n"
        else:
            status = "improved (but not yet completed)" if last_feedback.get("improved") else "no improvement"
            prompt += f"Score: {last_feedback.get('score')}\nStatus: {status}\n"
            if last_feedback.get("details", {}).get("stdout"):
                prompt += f"Eval output:\n{str(last_feedback['details']['stdout'])[:300]}\n"
            prompt += "\nAnalyze the eval output and your score. Find ways to improve.\n"
    elif not my_best_answer:
        prompt += "\nThis is your first attempt. Think carefully.\n"

    # Tool usage guidance and evaluator-aligned submission rules.
    if is_code:
        prompt += (
            "\n## CRITICAL RULES\n"
            "1. Do NOT hardcode test data. Input comes via function parameters.\n"
            "2. Functions must work with ANY input.\n"
            "3. Use Bash to test your code before submitting your final answer.\n"
            "4. Your final answer must be raw executable Python code only.\n"
            "5. Do NOT wrap it in XML tags, markdown fences, or prose.\n"
            "6. The evaluator writes your submission directly to solution.py and executes it.\n\n"
            "## Code Restrictions (enforced by sandbox)\n"
            "- Banned imports: os, subprocess, sys, shutil, signal, ctypes, socket, http, "
            "urllib, requests, httpx, importlib, pickle, shelve, marshal, multiprocessing, "
            "threading, concurrent, pathlib\n"
            "- Banned calls: eval(), exec(), compile(), __import__()\n"
            "- Max code size: 5MB\n"
            "- Code that violates these restrictions will be rejected with score 0.\n\n"
        )
    elif eval_type == "llm_judge":
        prompt += "\n## APPROACH\nUse WebSearch and WebFetch to research the topic. Verify facts before answering.\n\n"

    return prompt


def _parse_response(text):
    think_match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
    answer_match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
    thinking = think_match.group(1).strip() if think_match else text
    answer = answer_match.group(1).strip() if answer_match else text.strip()
    # Strip code fences
    answer = re.sub(r"```[\w]*\s*\n?", "", answer)
    answer = re.sub(r"\n?\s*```", "", answer)
    return thinking, answer.strip()


def call_llm(prompt, model, api_base=""):
    """Call LLM via litellm. Returns (thinking, answer, usage)."""
    # Set API keys from config
    config = load_config()
    keys = config.get("api_keys", {})
    for provider, env_var in [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY")]:
        if keys.get(provider) and not os.environ.get(env_var):
            os.environ[env_var] = keys[provider]

    # Guard: litellm's proxy_cli.py calls os.getcwd() at import time,
    # which crashes if the CWD no longer exists (e.g. deleted temp dir).
    try:
        os.getcwd()
    except (FileNotFoundError, OSError):
        os.chdir(os.path.expanduser("~"))

    import litellm
    litellm.suppress_debug_info = True
    from litellm import completion, completion_cost

    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 4096}
    if api_base:
        kwargs["api_base"] = api_base

    response = completion(**kwargs)
    text = response.choices[0].message.content

    usage = {}
    if hasattr(response, "usage") and response.usage:
        usage["prompt_tokens"] = getattr(response.usage, "prompt_tokens", 0) or 0
        usage["completion_tokens"] = getattr(response.usage, "completion_tokens", 0) or 0
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    try:
        usage["cost"] = completion_cost(completion_response=response) or 0.0
    except Exception:
        usage["cost"] = 0.0

    thinking, answer = _parse_response(text)
    return thinking, answer, usage
