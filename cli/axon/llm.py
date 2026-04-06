"""LLM integration — call Anthropic/OpenAI/Ollama via litellm."""
import re
import os

from axon.config import load_config


def build_prompt(task, my_best_answer, my_best_score, platform_best_score, last_feedback=None):
    direction_text = "higher is better" if task.get("direction") == "maximize" else "lower is better"
    is_code = task.get("eval_type") == "code_output"

    prompt = f"# Task: {task['title']}\n\n## Description\n{task['description']}\n\n"
    prompt += f"## Evaluation\nScored using: {task['eval_type']}\nDirection: {task['direction']} ({direction_text})\n"
    prompt += f"Completion threshold: {task['completion_threshold']}\n"
    prompt += f"Platform best: {platform_best_score if platform_best_score is not None else 'None (no submissions yet)'}\n"

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
        prompt += "\n## CRITICAL RULES\n1. Do NOT hardcode test data. Input comes via function parameters.\n2. Functions must work with ANY input.\n\n"

    prompt += f"## OUTPUT FORMAT\n<thinking>your reasoning</thinking>\n<answer>{'ONLY executable code, NO prose, NO markdown fences' if is_code else 'your answer'}</answer>\n"
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
