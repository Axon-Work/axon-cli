"""Mining loop — KeyWatcher, MiningDisplay, and run_mining (multi-task model)."""
from __future__ import annotations

import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from rich.live import Live

from axon.api import api_get, api_post
from axon.backends import create_backend
from axon.config import AXON_HOME, load_config
from axon.theme import console, branded_title
from axon.display import build_mining_panel, fmt_round, print_mining_summary, _fmt_usdc, BRAILLE_FRAMES
from axon.history import merge_server_history, build_local_record, build_error_record, append_record
from axon.llm import build_prompt, build_agent_prompt
from axon.session import load_session, save_session, delete_session


log = logging.getLogger("axon.mine")
PROMPT_LOG_DIR = AXON_HOME / "logs" / "prompts"
_UNSET = object()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_prompt_snapshot(task_id: str, round_num: int, prompt: str) -> Path | None:
    try:
        PROMPT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        path = PROMPT_LOG_DIR / f"{task_id}-round{round_num:03d}-{stamp}.txt"
        path.write_text(prompt, encoding="utf-8")
        return path
    except OSError:
        log.exception("Failed to write prompt snapshot task=%s round=%d", task_id, round_num)
        return None


def _usage_tokens(usage: dict) -> int | None:
    value = usage.get("tokens", usage.get("total_tokens"))
    return value if value is not None else None


def _usage_cost_usd(usage: dict) -> float | None:
    value = usage.get("cost_usd", usage.get("cost"))
    return value if value is not None else None


def _usage_billing_mode(usage: dict, backend_name: str) -> str:
    return usage.get("billing_mode") or ("subscription" if backend_name in ("codex-cli", "claude-cli") else "metered")


class KeyWatcher:
    """Background thread watching for ctrl+o / arrow keypresses."""

    def __init__(self) -> None:
        import threading
        self._show = False
        self._stop_event: threading.Event | None = None
        self.detail_idx: int = -1   # -1 = latest
        self.detail_count: int = 0  # set by mining loop

    @property
    def show_details(self) -> bool:
        return self._show

    def start(self) -> None:
        try:
            if not sys.stdin.isatty():
                return
        except (OSError, ValueError):
            return
        import threading
        self._stop_event = threading.Event()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self) -> None:
        import os, termios, select
        fd = sys.stdin.fileno()
        try:
            old = termios.tcgetattr(fd)
        except (OSError, termios.error):
            return
        try:
            # cbreak + disable IEXTEN so ctrl+o isn't swallowed as DISCARD
            new = termios.tcgetattr(fd)
            new[3] = new[3] & ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, new)
            while not self._stop_event.is_set():
                r, _, _ = select.select([sys.stdin], [], [], 0.15)
                if r:
                    ch = os.read(fd, 1)
                    if ch == b'\x0f':  # ctrl+o
                        self._show = not self._show
                        if self._show:
                            self.detail_idx = self.detail_count - 1
                    elif ch == b'\x1b':  # escape sequence (arrow keys)
                        r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r2:
                            seq = os.read(fd, 2)
                            if seq == b'[D' and self._show:  # left
                                self.detail_idx = max(0, self.detail_idx - 1)
                            elif seq == b'[C' and self._show:  # right
                                self.detail_idx = min(self.detail_count - 1, self.detail_idx + 1)
        except (OSError, termios.error):
            log.debug("KeyWatcher terminal I/O error", exc_info=True)
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except (OSError, termios.error):
                pass

    def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()


class MiningDisplay:
    """Dynamic renderable for Rich Live — compact status panel at bottom."""

    def __init__(self, watcher: KeyWatcher) -> None:
        self._watcher = watcher
        self.task_title: str = ""
        self.model: str = ""
        self.pool: int = 0
        self.threshold: float = 0.0
        self.best_score: float | None = None
        self.total_earned: int = 0
        self.round_count: int = 0
        self.status: str = ""
        self.total_tokens: int | None = 0
        self.total_cost: float | None = 0.0
        self.billing_mode: str = "metered"
        self.rounds: list[dict] = []
        self.all_details: list[dict] = []
        self.community_subs: list[dict] = []
        self.my_miner_id: str = ""
        self.max_rounds: int = 0
        self.budget: float = 0
        self.timeout: int = 0
        self.completion_reward_pct: int = 50
        self.call_started_at: float | None = None

    def __rich_console__(self, rconsole: Any, options: Any) -> Any:
        # Append elapsed time to status if LLM call is in progress
        status = self.status
        if self.call_started_at is not None:
            elapsed = int(time.monotonic() - self.call_started_at)
            frame = BRAILLE_FRAMES[int(time.monotonic() * 8) % len(BRAILLE_FRAMES)]
            status = f"{status} {frame} ({elapsed}s)"

        # Pick detail by watcher index, clamping to valid range
        idx = self._watcher.detail_idx
        if self.all_details:
            if idx < 0 or idx >= len(self.all_details):
                idx = len(self.all_details) - 1
            detail = self.all_details[idx]
        else:
            detail = None
        detail_nav = (idx + 1, len(self.all_details)) if self.all_details else None
        yield build_mining_panel(
            self.task_title, self.model, self.pool,
            self.threshold, self.best_score, self.total_earned,
            self.round_count, status, self._watcher.show_details,
            detail, self.rounds, detail_nav,
            total_tokens=self.total_tokens, total_cost=self.total_cost, billing_mode=self.billing_mode,
            community_subs=self.community_subs,
            my_miner_id=self.my_miner_id,
            max_rounds=self.max_rounds, budget=self.budget, timeout=self.timeout,
            completion_reward_pct=self.completion_reward_pct,
        )

    def __rich_measure__(self, rconsole: Any, options: Any) -> Any:
        from rich.measure import Measurement
        return Measurement(40, options.max_width)


def run_mining(task: dict, max_rounds: int, *, cli_timeout_override: int | None | object = _UNSET, budget: float = 0) -> None:
    """Mining loop: rounds scroll above, status panel stays at bottom."""
    config = load_config()
    backend_config = dict(config)
    if cli_timeout_override is not _UNSET:
        backend_config["cli_timeout"] = cli_timeout_override
    backend = create_backend(backend_config.get("backend", "litellm"), backend_config)
    model_name = config.get("default_model", "anthropic/claude-sonnet-4-20250514")

    task_id = task["id"]
    timeout_label = "none" if cli_timeout_override is None else (
        backend_config.get("cli_timeout") if cli_timeout_override is not _UNSET else config.get("cli_timeout", "")
    )
    log.info(
        "Mining config task=%s backend=%s max_rounds=%s cli_timeout=%s",
        task_id,
        backend.display_name(),
        "unlimited" if max_rounds <= 0 else max_rounds,
        timeout_label,
    )

    # Get best info
    try:
        best_info = api_get(f"/api/tasks/{task_id}/submissions/best", auth=False)
    except httpx.HTTPError:
        log.debug("Failed to fetch best submission info for %s", task_id, exc_info=True)
        best_info = {}

    my_best_answer = None
    my_best_score = None
    round_num = 0
    total_earned = 0
    total_tokens: int | None = 0
    total_cost: float | None = 0.0
    rounds_data: list[dict] = []
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    # Restore session (keyed by task_id)
    session_key = f"task-{task_id}"
    session = load_session(session_key)
    if session:
        my_best_answer = session.get("my_best_answer")
        my_best_score = session.get("my_best_score")
        total_earned = session.get("total_earned", 0)

    # Display state
    watcher = KeyWatcher()
    state = MiningDisplay(watcher)
    state.task_title = task["title"]
    state.model = backend.display_name()
    state.pool = task.get("pool_balance", 0)
    state.completion_reward_pct = task.get("completion_reward_pct", 50)
    state.threshold = task.get("completion_threshold", 0)
    state.best_score = my_best_score
    state.total_earned = total_earned
    state.round_count = round_num
    state.rounds = rounds_data
    state.billing_mode = "subscription" if backend.name in ("codex-cli", "claude-cli") else "metered"
    state.max_rounds = max_rounds
    state.budget = budget
    if cli_timeout_override is None:
        state.timeout = 0
    elif cli_timeout_override is _UNSET or not isinstance(cli_timeout_override, int):
        state.timeout = 0
    else:
        state.timeout = cli_timeout_override

    # Get my miner ID for community leaderboard highlighting
    try:
        me_info = api_get("/api/auth/me")
        state.my_miner_id = str(me_info.get("id", ""))
    except httpx.HTTPError:
        log.debug("Failed to fetch /me for miner id", exc_info=True)
        state.my_miner_id = ""

    # Load local history + merge server submissions (dedup)
    server_subs: list[dict] = []
    try:
        server_subs = api_get(f"/api/tasks/{task_id}/submissions/mine")
    except httpx.HTTPError:
        log.debug("Failed to fetch my submissions; local history only", exc_info=True)
    my_past_subs = merge_server_history(task_id, server_subs)

    last_feedback = None
    consecutive_dups = 0
    threshold = task.get("completion_threshold", 0)

    # Save terminal settings for cleanup
    old_tty = None
    try:
        if sys.stdin.isatty():
            import termios
            old_tty = termios.tcgetattr(sys.stdin.fileno())
    except (OSError, ValueError, ImportError):
        pass

    try:
        watcher.start()

        with Live(state, console=console, refresh_per_second=4) as live:
            while True:
                round_num += 1
                _budget_exceeded = False
                if max_rounds > 0 and round_num > max_rounds:
                    break

                # LLM stuck
                if consecutive_dups >= 3:
                    console.print("  [warning]3 consecutive duplicates — stopping.[/]")
                    break

                state.round_count = round_num
                state.status = f"[secondary]► Round {round_num}  calling {backend.display_name()}...[/]"
                round_started_at = _now_iso()
                round_started_mono = time.monotonic()
                log.info(
                    "Round %d start task=%s title=%r backend=%s started_at=%s",
                    round_num,
                    task_id,
                    task.get("title", ""),
                    backend.display_name(),
                    round_started_at,
                )

                # --- Call Backend ---
                try:
                    # Fetch community submissions for context
                    try:
                        all_subs = api_get(f"/api/tasks/{task_id}/submissions?limit=10", auth=False)
                        community_subs = [s for s in all_subs if s.get("score") is not None and s.get("is_improvement")]
                        community_subs.sort(key=lambda s: s.get("score", 0), reverse=(task.get("direction") == "maximize"))
                    except httpx.HTTPError:
                        log.debug("Failed to fetch community submissions", exc_info=True)
                        all_subs = []
                        community_subs = []

                    state.community_subs = community_subs

                    if backend.name == "litellm":
                        prompt = build_prompt(task, my_best_answer, my_best_score, best_info.get("score"), last_feedback, community_subs=community_subs, my_past_subs=my_past_subs)
                    else:
                        prompt = build_agent_prompt(task, my_best_answer, my_best_score, best_info.get("score"), last_feedback, community_subs=community_subs, my_past_subs=my_past_subs)

                    prompt_path = _write_prompt_snapshot(task_id, round_num, prompt)
                    log.info(
                        "Round %d prompt task=%s chars=%d lines=%d community_subs=%d my_past_subs=%d path=%s",
                        round_num,
                        task_id,
                        len(prompt),
                        prompt.count("\n") + 1 if prompt else 0,
                        len(community_subs),
                        len(my_past_subs),
                        str(prompt_path) if prompt_path else "",
                    )
                    state.call_started_at = time.monotonic()
                    result = backend.call(prompt, task)
                    state.call_started_at = None
                    thinking, answer, usage = result["thinking"], result["answer"], result["usage"]
                    billing_mode = _usage_billing_mode(usage, backend.name)
                    state.billing_mode = billing_mode
                    tokens_used = _usage_tokens(usage)
                    cost_usd = _usage_cost_usd(usage)
                    if billing_mode == "metered":
                        total_tokens = (total_tokens or 0) + (tokens_used or 0)
                        total_cost = (total_cost or 0.0) + (cost_usd or 0.0)
                    else:
                        total_tokens = None
                        total_cost = None
                    state.total_tokens = total_tokens
                    state.total_cost = total_cost
                    # Budget check — submit this round's answer before stopping
                    _budget_exceeded = (budget > 0 and total_cost is not None and total_cost >= budget)
                    log.info(
                        "Round %d backend_done task=%s finished_at=%s duration_s=%.2f answer_chars=%d thinking_chars=%d billing_mode=%s total_tokens=%s cost_usd=%s",
                        round_num,
                        task_id,
                        _now_iso(),
                        time.monotonic() - round_started_mono,
                        len(answer or ""),
                        len(thinking or ""),
                        billing_mode,
                        tokens_used,
                        cost_usd,
                    )
                except Exception as e:
                    state.call_started_at = None
                    consecutive_errors += 1
                    record = build_error_record(task_id, None, None, None, None, round_num, state.billing_mode, "crash", str(e))
                    append_record(task_id, record)
                    rounds_data.append({"round": round_num, "score": None, "result": "crash", "earned": 0})
                    state.all_details.append({"score": None, "result": "crash", "earned": 0,
                                              "error": str(e), "eval_details": None, "answer": None, "thinking": None})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error(
                        "Round %d backend_error task=%s finished_at=%s duration_s=%.2f error=%s",
                        round_num,
                        task_id,
                        _now_iso(),
                        time.monotonic() - round_started_mono,
                        e,
                        exc_info=True,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        console.print(f"  [warning]{MAX_CONSECUTIVE_ERRORS} consecutive errors — stopping.[/]")
                        break
                    sleep_time = 10 if isinstance(e, TimeoutError) else 2
                    time.sleep(sleep_time)
                    continue

                state.status = f"[secondary]► Round {round_num}  submitting...[/]"
                state.call_started_at = time.monotonic()

                # --- Submit to task ---
                thinking = thinking or "(no reasoning provided)"
                try:
                    sub = api_post(f"/api/tasks/{task_id}/submissions", {
                        "answer": answer, "thinking": thinking, "llm_model_used": backend.display_name(),
                    })
                except httpx.HTTPStatusError as e:
                    state.call_started_at = None
                    code = e.response.status_code
                    if code == 402:
                        detail_msg = ""
                        try:
                            detail_msg = e.response.json().get("detail", "")
                        except (ValueError, AttributeError):
                            pass
                        console.print(f"  [warning]Insufficient balance for GPU eval. {detail_msg}[/]")
                        console.print(f"  [secondary]Mine CPU tasks first or deposit USDC to continue.[/]")
                        break
                    if code == 429:
                        import re
                        detail_msg = e.response.json().get("detail", "")
                        wait = int(m.group(1)) if (m := re.search(r"(\d+)s", detail_msg)) else 10
                        record = build_error_record(task_id, answer, thinking,
                            _usage_tokens(usage), _usage_cost_usd(usage),
                            round_num, state.billing_mode, "rate limited", detail_msg)
                        append_record(task_id, record)
                        rounds_data.append({"round": round_num, "score": None, "result": "rate limited", "earned": 0})
                        state.all_details.append({"score": None, "result": "rate limited", "earned": 0,
                                                  "error": detail_msg, "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        state.status = f"[warning]► rate limited, waiting {wait}s...[/]"
                        log.warning(
                            "Round %d end task=%s status=rate_limited finished_at=%s duration_s=%.2f wait_s=%d detail=%s",
                            round_num,
                            task_id,
                            _now_iso(),
                            time.monotonic() - round_started_mono,
                            wait,
                            detail_msg,
                        )
                        time.sleep(wait)
                        continue
                    if code == 409:
                        consecutive_dups += 1
                        record = build_error_record(task_id, answer, thinking,
                            _usage_tokens(usage), _usage_cost_usd(usage),
                            round_num, state.billing_mode, "duplicate", "duplicate answer")
                        append_record(task_id, record)
                        rounds_data.append({"round": round_num, "score": None, "result": "duplicate", "earned": 0})
                        state.all_details.append({"score": None, "result": "duplicate", "earned": 0,
                                                  "error": "duplicate answer", "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        state.status = ""
                        log.info(
                            "Round %d end task=%s status=duplicate finished_at=%s duration_s=%.2f consecutive_duplicates=%d",
                            round_num,
                            task_id,
                            _now_iso(),
                            time.monotonic() - round_started_mono,
                            consecutive_dups,
                        )
                        continue
                    if code == 422:
                        consecutive_errors += 1
                        detail_msg = ""
                        try:
                            detail_msg = e.response.text[:500]
                        except (ValueError, AttributeError):
                            pass
                        error_msg = f"422 validation error: {detail_msg}" if detail_msg else str(e)
                        record = build_error_record(task_id, answer, thinking,
                            _usage_tokens(usage), _usage_cost_usd(usage),
                            round_num, state.billing_mode, "validation error", error_msg)
                        append_record(task_id, record)
                        rounds_data.append({"round": round_num, "score": None, "result": "validation error", "earned": 0})
                        state.all_details.append({"score": None, "result": "validation error", "earned": 0,
                                                  "error": error_msg, "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        state.status = ""
                        log.warning(
                            "Round %d end task=%s status=validation_error finished_at=%s duration_s=%.2f error=%s",
                            round_num,
                            task_id,
                            _now_iso(),
                            time.monotonic() - round_started_mono,
                            error_msg,
                        )
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            console.print(f"  [warning]{MAX_CONSECUTIVE_ERRORS} consecutive errors — stopping.[/]")
                            break
                        continue
                    if code == 400:
                        detail_msg = ""
                        try:
                            detail_msg = e.response.json().get("detail", "")
                        except (ValueError, AttributeError):
                            pass
                        if "completed" in detail_msg or "closed" in detail_msg:
                            console.print(f"  [warning]Task is no longer open. Stopping.[/]")
                            break
                    if code == 404:
                        console.print("  [warning]Task not found. Stopping.[/]")
                        break
                    # Log response body for debugging
                    consecutive_errors += 1
                    resp_detail = ""
                    try:
                        resp_detail = e.response.text[:500]
                    except (ValueError, AttributeError):
                        pass
                    error_msg = f"{e} — {resp_detail}" if resp_detail else str(e)
                    record = build_error_record(task_id, answer, thinking,
                        _usage_tokens(usage), _usage_cost_usd(usage),
                        round_num, state.billing_mode, "error", error_msg)
                    append_record(task_id, record)
                    rounds_data.append({"round": round_num, "score": None, "result": "error", "earned": 0})
                    state.all_details.append({"score": None, "result": "error", "earned": 0,
                                              "error": error_msg, "eval_details": None, "answer": answer, "thinking": thinking})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error(
                        "Round %d end task=%s status=submit_error finished_at=%s duration_s=%.2f error=%s body=%s",
                        round_num,
                        task_id,
                        _now_iso(),
                        time.monotonic() - round_started_mono,
                        e,
                        resp_detail,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        console.print(f"  [warning]{MAX_CONSECUTIVE_ERRORS} consecutive errors — stopping.[/]")
                        break
                    time.sleep(2)
                    continue
                except Exception as e:
                    state.call_started_at = None
                    consecutive_errors += 1
                    record = build_error_record(task_id, answer, thinking,
                        _usage_tokens(usage), _usage_cost_usd(usage),
                        round_num, state.billing_mode, "crash", str(e))
                    append_record(task_id, record)
                    rounds_data.append({"round": round_num, "score": None, "result": "crash", "earned": 0})
                    state.all_details.append({"score": None, "result": "crash", "earned": 0,
                                              "error": str(e), "eval_details": None, "answer": answer, "thinking": thinking})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error(
                        "Round %d end task=%s status=submit_crash finished_at=%s duration_s=%.2f error=%s",
                        round_num,
                        task_id,
                        _now_iso(),
                        time.monotonic() - round_started_mono,
                        e,
                        exc_info=True,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        console.print(f"  [warning]{MAX_CONSECUTIVE_ERRORS} consecutive errors — stopping.[/]")
                        break
                    time.sleep(2)
                    continue

                # --- Poll for async eval completion ---
                state.call_started_at = None  # clear submit timer

                if sub.get("eval_status") == "pending":
                    state.call_started_at = time.monotonic()
                    state.status = f"[secondary]► Round {round_num}  evaluating...[/]"
                    poll_interval = 1
                    max_wait = 120
                    waited = 0
                    while sub.get("eval_status") == "pending" and waited < max_wait:
                        time.sleep(poll_interval)
                        waited += poll_interval
                        try:
                            sub = api_get(f"/api/tasks/{task_id}/submissions/{sub['id']}")
                        except httpx.HTTPError:
                            log.debug("Poll hiccup for submission %s", sub.get("id"), exc_info=True)

                    state.call_started_at = None  # clear eval timer

                    if sub.get("eval_status") == "pending":
                        # Timed out waiting for eval
                        rounds_data.append({"round": round_num, "score": None, "result": "eval timeout", "earned": 0})
                        state.all_details.append({"score": None, "result": "eval timeout", "earned": 0,
                                                   "error": "eval timed out", "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        consecutive_errors += 1
                        state.status = ""
                        log.warning("Round %d eval timeout task=%s", round_num, task_id)
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            console.print(f"  [warning]{MAX_CONSECUTIVE_ERRORS} consecutive errors — stopping.[/]")
                            break
                        continue

                # --- Process result ---
                consecutive_dups = 0
                consecutive_errors = 0
                score = sub.get("score")
                earned = sub.get("reward_earned", 0)
                total_earned += earned
                is_completion = sub.get("is_completion", False)
                is_improvement = sub.get("is_improvement", False)
                error = sub.get("eval_error")

                if error:
                    result_label = "eval error"
                elif is_completion:
                    result_label = "COMPLETE"
                elif is_improvement:
                    result_label = "improved"
                else:
                    result_label = "no change"

                record = build_local_record(sub, answer, thinking,
                    _usage_tokens(usage), _usage_cost_usd(usage),
                    round_num, state.billing_mode, result_label)
                append_record(task_id, record)
                my_past_subs.append(record)

                rounds_data.append({"round": round_num, "score": score, "result": result_label, "earned": earned})
                state.all_details.append({
                    "score": score, "result": result_label, "earned": earned,
                    "error": error, "eval_details": sub.get("eval_details"),
                    "answer": answer, "thinking": thinking,
                })
                watcher.detail_count = len(state.all_details)
                state.total_earned = total_earned

                # --- Update state ---
                last_feedback = {
                    "score": score,
                    "error": error,
                    "details": sub.get("eval_details"),
                    "improved": is_improvement,
                    "answer": answer,
                }
                if is_improvement:
                    my_best_answer = answer
                    my_best_score = score
                    state.best_score = my_best_score

                log.info(
                    "Round %d end task=%s status=%s finished_at=%s duration_s=%.2f score=%s earned=%s improvement=%s completion=%s eval_error=%s",
                    round_num,
                    task_id,
                    result_label,
                    _now_iso(),
                    time.monotonic() - round_started_mono,
                    score,
                    earned,
                    is_improvement,
                    is_completion,
                    error,
                )

                save_session(session_key, {
                    "my_best_answer": my_best_answer,
                    "my_best_score": my_best_score,
                    "round_num": round_num,
                    "total_earned": total_earned,
                    "model": backend.display_name(),
                })

                # Refresh pool from server
                try:
                    task_check = api_get(f"/api/tasks/{task_id}", auth=False)
                    state.pool = task_check.get("pool_balance", state.pool)
                    state.completion_reward_pct = task_check.get("completion_reward_pct", state.completion_reward_pct)
                    task_status = task_check.get("status", "open")
                except httpx.HTTPError:
                    log.debug("Failed to refresh task state", exc_info=True)
                    task_status = "open"

                if is_completion:
                    delete_session(session_key)
                    state.status = f"[result.complete]✓ Task completed! Earned {_fmt_usdc(total_earned)}[/]"
                    time.sleep(1)
                    break

                # Task closed by pool exhaustion or admin
                if task_status != "open":
                    delete_session(session_key)
                    console.print("  [warning]Task ended. Stopping.[/]")
                    break

                # Budget exceeded — stop after submitting this round
                if _budget_exceeded:
                    console.print(f"  [warning]Budget limit reached (${budget:.2f}). Stopping.[/]")
                    break

                state.status = ""

    except KeyboardInterrupt:
        console.print("\n  [warning]Mining stopped. Session saved — run again to resume.[/]")
    finally:
        watcher.stop()
        if old_tty is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_tty)
            except (OSError, ValueError, ImportError):
                pass

    # --- Summary ---
    notable = [r for r in rounds_data if r["result"] != "no change"]
    if notable:
        print_mining_summary(notable, my_best_score, total_earned, round_num,
                             total_tokens=total_tokens, total_cost=total_cost, billing_mode=state.billing_mode)
    else:
        best = f"{my_best_score:.6f}" if my_best_score is not None else "N/A"
        if state.billing_mode == "subscription":
            token_str = "unknown" if total_tokens is None else f"{total_tokens:,}"
            cost_str = "subscription"
        else:
            token_str = f"{(total_tokens or 0):,}"
            cost_str = f"${total_cost:.4f}" if total_cost else "$0"
        console.print(f"\n  {branded_title('Mining Summary')}")
        console.print(f"  Best:    {best}")
        console.print(f"  Earned:  [money]{_fmt_usdc(total_earned)}[/]")
        console.print(f"  Tokens:  {token_str}  Cost: [warning]{cost_str}[/]")
        console.print(f"  Rounds:  {round_num}\n")
