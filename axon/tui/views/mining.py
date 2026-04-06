"""Mining view — real-time mining dashboard."""
import logging

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Static, DataTable

from axon.api import api_get, api_post
from axon.config import load_config
from axon.session import load_session, save_session, delete_session

log = logging.getLogger("axon.tui")


class BackFromMining(Message):
    pass


class MiningView(VerticalScroll):
    def __init__(self, task_id: str, max_rounds: int = 0):
        super().__init__()
        self.task_id = task_id
        self.max_rounds = max_rounds
        self.rounds: list[dict] = []
        self.best_score = None
        self.total_earned = 0
        self.mining = False
        self.show_debug = False
        self.debug_idx = 0
        self.all_responses: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static("[bold gold1]ψ Mining[/]", id="mine-title")
        yield Static("Loading...", id="mine-status")
        yield Static("", id="mine-rounds")
        yield Static("", id="mine-debug")
        yield Static("[dim green]ctrl+o: response  ·  ← →: browse  ·  Esc: stop[/]", id="mine-footer")

    def on_mount(self):
        self.mining = True
        self._app_ref = self.app  # cache before entering worker thread
        self._app_ref.run_worker(self._mine_loop, thread=True, exclusive=True)

    async def _mine_loop(self):
        try:
            task = api_get(f"/api/tasks/{self.task_id}", auth=False)
            self._app_ref.call_from_thread(self._update_title, task)

            best_info = api_get(f"/api/tasks/{self.task_id}/submissions/best")
            config = load_config()
            model = config.get("default_model", "anthropic/claude-sonnet-4-20250514")
            api_base = config.get("api_base", "")

            my_best_answer = None
            my_best_score = None
            round_num = 0

            # Restore session
            session = load_session(self.task_id)
            if session:
                my_best_answer = session.get("my_best_answer")
                my_best_score = session.get("my_best_score")
                round_num = session.get("round_num", 0)
                self.total_earned = session.get("total_earned", 0)

            last_feedback = None
            while self.mining:
                round_num += 1
                if self.max_rounds > 0 and round_num > self.max_rounds:
                    break

                self._app_ref.call_from_thread(self._update_status, f"Round {round_num}: calling {model}...")

                # Call LLM
                try:
                    from axon.llm import build_prompt, call_llm
                    prompt = build_prompt(task, my_best_answer, my_best_score, best_info.get("score"), last_feedback)
                    thinking, answer, usage = call_llm(prompt, model, api_base)
                except Exception as e:
                    self._app_ref.call_from_thread(self._add_round, round_num, None, False, 0, str(e))
                    import time; time.sleep(2)
                    continue

                # Submit
                self._app_ref.call_from_thread(self._update_status, f"Round {round_num}: submitting...")
                try:
                    sub = api_post(f"/api/tasks/{self.task_id}/submissions", {
                        "answer": answer, "thinking": thinking, "llm_model_used": model,
                    })
                except Exception as e:
                    self._app_ref.call_from_thread(self._add_round, round_num, None, False, 0, str(e))
                    import time; time.sleep(2)
                    continue

                earned = sub.get("reward_earned", 0)
                self.total_earned += earned
                self.all_responses.append(sub)

                self._app_ref.call_from_thread(
                    self._add_round, round_num, sub.get("score"), sub.get("is_improvement", False),
                    earned, sub.get("eval_error"),
                )

                last_feedback = {
                    "score": sub.get("score"),
                    "error": sub.get("eval_error"),
                    "details": sub.get("eval_details"),
                    "improved": sub.get("is_improvement", False),
                    "answer": answer,
                }

                if sub.get("is_improvement"):
                    my_best_answer = answer
                    my_best_score = sub["score"]
                    self.best_score = my_best_score

                save_session(self.task_id, {
                    "my_best_answer": my_best_answer,
                    "my_best_score": my_best_score,
                    "round_num": round_num,
                    "total_earned": self.total_earned,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "model": model,
                })

                if sub.get("is_completion"):
                    delete_session(self.task_id)
                    self._app_ref.call_from_thread(self._update_status, "[bold green]Task completed![/]")
                    break

                # Check task status
                task_check = api_get(f"/api/tasks/{self.task_id}", auth=False)
                if task_check.get("status") not in ("open", "completed"):
                    break

        except Exception as e:
            log.error("Mining loop error: %s", e, exc_info=True)
            try:
                self._app_ref.call_from_thread(self._update_status, f"[red]Error: {e}[/]")
            except Exception:
                pass

        self.mining = False
        try:
            self._app_ref.call_from_thread(self._show_summary)
        except Exception:
            pass

    def _query(self, selector: str) -> Static | None:
        """Safe query — returns None if the widget was already removed."""
        try:
            return self.query_one(selector, Static)
        except NoMatches:
            self.mining = False
            return None

    def _update_title(self, task: dict):
        w = self._query("#mine-title")
        if w:
            w.update(
                f"[bold gold1]ψ Mining: {task['title']}[/]\n"
                f"  Threshold: {task['completion_threshold']}  Pool: [green]{task['pool_balance']} $AXN[/]"
            )

    def _update_status(self, text: str):
        w = self._query("#mine-status")
        if w:
            w.update(text)

    def _add_round(self, num: int, score, improved: bool, earned: int, error: str | None):
        self.rounds.append({"num": num, "score": score, "improved": improved, "earned": earned, "error": error})
        lines = []
        for r in self.rounds:
            s = f"{r['score']:.6f}" if r["score"] is not None else "ERROR"
            if r["error"]:
                lines.append(f"  [red]R{r['num']:2d}  {s:>12}  ✗ error[/]")
            elif r["improved"]:
                earned_str = f"+{r['earned']} $AXN" if r["earned"] else ""
                lines.append(f"  [green]R{r['num']:2d}  {s:>12}  ✓ improved  {earned_str}[/]")
            else:
                lines.append(f"  [dim]R{r['num']:2d}  {s:>12}  · no change[/]")
        w = self._query("#mine-rounds")
        if w:
            w.update("\n".join(lines))

    def _show_summary(self):
        best = f"{self.best_score:.6f}" if self.best_score is not None else "N/A"
        self._update_status(
            f"[bold]Summary[/]\n"
            f"  Best score:   {best}\n"
            f"  Total earned: [green]{self.total_earned} $AXN[/]\n"
            f"  Rounds:       {len(self.rounds)}"
        )
        w = self._query("#mine-footer")
        if w:
            w.update("[dim green]ctrl+o: response  ·  ← →: browse  ·  q: back[/]")

    def _render_debug(self):
        if not self.show_debug or not self.all_responses:
            w = self._query("#mine-debug")
            if w:
                w.update("")
            return
        import json
        resp = self.all_responses[self.debug_idx]
        content = json.dumps({
            "score": resp.get("score"),
            "is_improvement": resp.get("is_improvement"),
            "eval_status": resp.get("eval_status"),
            "eval_error": resp.get("eval_error"),
            "eval_details": resp.get("eval_details"),
            "reward_earned": resp.get("reward_earned"),
        }, indent=2)[:1000]
        w = self._query("#mine-debug")
        if w:
            w.update(
                f"\n[bold cyan]Round {self.debug_idx + 1}/{len(self.all_responses)}  ← prev  → next  ctrl+o hide[/]\n"
                f"[dim]{content}[/]"
            )

    def key_ctrl_o(self):
        self.show_debug = not self.show_debug
        if self.show_debug and self.all_responses:
            self.debug_idx = len(self.all_responses) - 1
        self._render_debug()

    def key_left(self):
        if self.show_debug and self.debug_idx > 0:
            self.debug_idx -= 1
            self._render_debug()

    def key_right(self):
        if self.show_debug and self.debug_idx < len(self.all_responses) - 1:
            self.debug_idx += 1
            self._render_debug()

    def key_escape(self):
        self.mining = False
        self.post_message(BackFromMining())

    def key_q(self):
        if not self.mining:
            self.post_message(BackFromMining())
