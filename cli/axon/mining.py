"""Mining loop — KeyWatcher, MiningDisplay, and run_mining."""
import sys
import time
import logging

import httpx
from rich.live import Live

from axon.api import api_get, api_post
from axon.config import load_config
from axon.display import console, build_mining_panel, fmt_round, print_mining_summary
from axon.llm import build_prompt, call_llm
from axon.session import load_session, save_session, delete_session


log = logging.getLogger("axon.mine")


class KeyWatcher:
    """Background thread watching for ctrl+o / arrow keypresses."""

    def __init__(self):
        self._show = False
        self._stop_event = None
        self.detail_idx: int = -1   # -1 = latest
        self.detail_count: int = 0  # set by mining loop

    @property
    def show_details(self) -> bool:
        return self._show

    def start(self):
        try:
            if not sys.stdin.isatty():
                return
        except Exception:
            return
        import threading
        self._stop_event = threading.Event()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        import os, termios, select
        fd = sys.stdin.fileno()
        try:
            old = termios.tcgetattr(fd)
        except Exception:
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
        except Exception:
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass

    def stop(self):
        if self._stop_event:
            self._stop_event.set()


class MiningDisplay:
    """Dynamic renderable for Rich Live — compact status panel at bottom."""

    def __init__(self, watcher: KeyWatcher):
        self._watcher = watcher
        self.task_title: str = ""
        self.model: str = ""
        self.pool: int = 0
        self.threshold: float = 0.0
        self.best_score: float | None = None
        self.total_earned: int = 0
        self.round_count: int = 0
        self.status: str = ""
        self.rounds: list[dict] = []
        self.all_details: list[dict] = []

    def __rich_console__(self, rconsole, options):
        # Pick detail by watcher index
        idx = self._watcher.detail_idx
        detail = self.all_details[idx] if 0 <= idx < len(self.all_details) else None
        detail_nav = (idx + 1, len(self.all_details)) if self.all_details else None
        yield build_mining_panel(
            self.task_title, self.model, self.pool,
            self.threshold, self.best_score, self.total_earned,
            self.round_count, self.status, self._watcher.show_details,
            detail, self.rounds, detail_nav,
        )

    def __rich_measure__(self, rconsole, options):
        from rich.measure import Measurement
        return Measurement(40, options.max_width)


def run_mining(task_id: str, max_rounds: int):
    """Mining loop: rounds scroll above, status panel stays at bottom."""
    task = api_get(f"/api/tasks/{task_id}", auth=False)
    best_info = api_get(f"/api/tasks/{task_id}/submissions/best")
    config = load_config()
    model_name = config.get("default_model", "anthropic/claude-sonnet-4-20250514")
    api_base = config.get("api_base", "")

    my_best_answer = None
    my_best_score = None
    round_num = 0
    total_earned = 0
    rounds_data: list[dict] = []

    # Restore session
    session = load_session(task_id)
    if session:
        my_best_answer = session.get("my_best_answer")
        my_best_score = session.get("my_best_score")
        round_num = session.get("round_num", 0)
        total_earned = session.get("total_earned", 0)

    # Display state
    watcher = KeyWatcher()
    state = MiningDisplay(watcher)
    state.task_title = task["title"]
    state.model = model_name
    state.pool = task["pool_balance"]
    state.threshold = task["completion_threshold"]
    state.best_score = my_best_score
    state.total_earned = total_earned
    state.round_count = round_num
    state.rounds = rounds_data  # shared reference — appends are visible to panel

    last_feedback = None
    consecutive_dups = 0
    threshold = task["completion_threshold"]

    # Save terminal settings for cleanup
    old_tty = None
    try:
        if sys.stdin.isatty():
            import termios
            old_tty = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    try:
        watcher.start()

        with Live(state, console=console, refresh_per_second=4) as live:
            while True:
                round_num += 1
                if max_rounds > 0 and round_num > max_rounds:
                    break

                # Already reached threshold — nothing more to do
                if my_best_score is not None and my_best_score >= threshold:
                    state.status = "[bold green]✓ Threshold reached![/]"
                    time.sleep(1)
                    break

                # LLM stuck generating same answers
                if consecutive_dups >= 3:
                    console.print("  [yellow]3 consecutive duplicates — LLM has no new ideas. Stopping.[/]")
                    break

                state.round_count = round_num
                state.status = f"[dim]► R{round_num}  calling LLM...[/]"

                # --- Call LLM ---
                try:
                    prompt = build_prompt(task, my_best_answer, my_best_score, best_info.get("score"), last_feedback)
                    thinking, answer, usage = call_llm(prompt, model_name, api_base)
                except Exception as e:
                    rounds_data.append({"round": round_num, "score": None, "result": "crash", "earned": 0})
                    state.all_details.append({"score": None, "result": "crash", "earned": 0,
                                              "error": str(e), "eval_details": None, "answer": None, "thinking": None})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error("LLM error round %d: %s", round_num, e, exc_info=True)
                    time.sleep(2)
                    continue

                state.status = f"[dim]► R{round_num}  submitting...[/]"

                # --- Submit ---
                try:
                    sub = api_post(f"/api/tasks/{task_id}/submissions", {
                        "answer": answer, "thinking": thinking, "llm_model_used": model_name,
                    })
                except httpx.HTTPStatusError as e:
                    code = e.response.status_code
                    if code == 429:
                        import re
                        detail_msg = e.response.json().get("detail", "")
                        wait = int(m.group(1)) if (m := re.search(r"(\d+)s", detail_msg)) else 10
                        rounds_data.append({"round": round_num, "score": None, "result": "rate limited", "earned": 0})
                        state.all_details.append({"score": None, "result": "rate limited", "earned": 0,
                                                  "error": detail_msg, "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        state.status = f"[dim yellow]► rate limited, waiting {wait}s...[/]"
                        log.warning("Rate limited round %d: %s", round_num, detail_msg)
                        time.sleep(wait)
                        continue
                    if code == 409:
                        consecutive_dups += 1
                        rounds_data.append({"round": round_num, "score": None, "result": "duplicate", "earned": 0})
                        state.all_details.append({"score": None, "result": "duplicate", "earned": 0,
                                                  "error": "duplicate answer", "eval_details": None, "answer": answer, "thinking": thinking})
                        watcher.detail_count = len(state.all_details)
                        state.status = ""
                        log.info("Duplicate answer round %d (%d consecutive)", round_num, consecutive_dups)
                        continue
                    rounds_data.append({"round": round_num, "score": None, "result": "error", "earned": 0})
                    state.all_details.append({"score": None, "result": "error", "earned": 0,
                                              "error": str(e), "eval_details": None, "answer": answer, "thinking": thinking})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error("Submit error round %d: %s", round_num, e, exc_info=True)
                    time.sleep(2)
                    continue
                except Exception as e:
                    rounds_data.append({"round": round_num, "score": None, "result": "crash", "earned": 0})
                    state.all_details.append({"score": None, "result": "crash", "earned": 0,
                                              "error": str(e), "eval_details": None, "answer": answer, "thinking": thinking})
                    watcher.detail_count = len(state.all_details)
                    state.status = ""
                    log.error("Submit error round %d: %s", round_num, e, exc_info=True)
                    time.sleep(2)
                    continue

                # --- Process result ---
                consecutive_dups = 0
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

                rounds_data.append({"round": round_num, "score": score, "result": result_label, "earned": earned})
                state.all_details.append({
                    "score": score, "result": result_label, "earned": earned,
                    "error": error, "eval_details": sub.get("eval_details"),
                    "answer": answer, "thinking": thinking,
                })
                watcher.detail_count = len(state.all_details)
                state.status = ""
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

                save_session(task_id, {
                    "my_best_answer": my_best_answer,
                    "my_best_score": my_best_score,
                    "round_num": round_num,
                    "total_earned": total_earned,
                    "model": model_name,
                })

                if is_completion:
                    delete_session(task_id)
                    state.status = "[bold green]✓ Task completed![/]"
                    time.sleep(1)
                    break

                # Check task still open
                task_check = api_get(f"/api/tasks/{task_id}", auth=False)
                if task_check.get("status") not in ("open",):
                    console.print(f"  [yellow]Task {task_check.get('status')}[/]")
                    break

    except KeyboardInterrupt:
        console.print("\n  [yellow]Mining stopped. Session saved — run again to resume.[/]")
    finally:
        watcher.stop()
        if old_tty is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_tty)
            except Exception:
                pass

    # --- Summary ---
    notable = [r for r in rounds_data if r["result"] != "no change"]
    if notable:
        print_mining_summary(notable, my_best_score, total_earned, round_num)
    else:
        best = f"{my_best_score:.6f}" if my_best_score is not None else "N/A"
        console.print(f"\n  [bold gold1]ψ Mining Summary[/]")
        console.print(f"  Best:    {best}")
        console.print(f"  Earned:  [green]{total_earned} $AXN[/]")
        console.print(f"  Rounds:  {round_num}\n")
