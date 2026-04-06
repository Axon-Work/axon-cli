"""Task list view — DataTable of all tasks (completed ones greyed out)."""
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Static


class MineTaskRequested(Message):
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id


class ViewTaskRequested(Message):
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id


class TaskListView(Vertical):
    def __init__(self, tasks: list[dict]):
        super().__init__()
        self.tasks = tasks

    def compose(self) -> ComposeResult:
        open_count = sum(1 for t in self.tasks if t.get("status") == "open")
        total = len(self.tasks)
        yield Static(f"[bold gold1]ψ Tasks[/] ({open_count} open / {total} total)", id="view-title")
        table = DataTable(id="task-table")
        table.cursor_type = "row"
        table.add_columns("ID", "Title", "Eval", "Status", "Best", "Pool")
        for t in self.tasks:
            best = f"{t.get('best_score', 0):.2f}" if t.get("best_score") is not None else "-"
            status = t.get("status", "open")
            dim = status in ("completed", "closed")
            style = "dim" if dim else ""
            table.add_row(
                Text(str(t["id"])[:8], style=style),
                Text(t["title"][:40], style=style),
                Text(t["eval_type"], style=style),
                Text(status, style="dim italic" if dim else "bold green"),
                Text(best, style=style),
                Text(str(t["pool_balance"]), style=style),
                key=t["id"],
            )
        yield table
        yield Static("[dim]Enter: view  ·  m: mine  ·  r: refresh[/]")

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key and event.row_key.value:
            self.post_message(ViewTaskRequested(str(event.row_key.value)))

    def key_m(self):
        table = self.query_one("#task-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None and row_key < len(self.tasks):
            self.post_message(MineTaskRequested(self.tasks[row_key]["id"]))
