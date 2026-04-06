"""Task detail view."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static


class BackToList(Message):
    pass


class StartMining(Message):
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id


class TaskDetailView(VerticalScroll):
    def __init__(self, task: dict):
        super().__init__()
        self.task = task

    def compose(self) -> ComposeResult:
        t = self.task
        yield Static(f"[bold gold1]ψ {t['title']}[/]")
        yield Static("")
        yield Static(f"  ID:        [cyan]{t['id']}[/]")
        yield Static(f"  Eval:      {t['eval_type']} ({t['direction']})")
        yield Static(f"  Status:    {t['status']}")
        yield Static(f"  Threshold: {t['completion_threshold']}")
        best = f"{t['best_score']:.4f}" if t.get("best_score") is not None else "-"
        yield Static(f"  Best:      {best}")
        baseline = f"{t['baseline_score']:.4f}" if t.get("baseline_score") is not None else "-"
        yield Static(f"  Baseline:  {baseline}")
        yield Static(f"  Staked:    [red]{t['task_burn']} $AXN[/]")
        yield Static(f"  Pool:      [green]{t['pool_balance']} $AXN[/]")
        yield Static("")
        yield Static(f"[dim]{t['description']}[/]")
        yield Static("")
        yield Static("[dim]m: mine this task  ·  Esc: back[/]")

    def key_escape(self):
        self.post_message(BackToList())

    def key_m(self):
        self.post_message(StartMining(self.task["id"]))
