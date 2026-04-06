"""Main screen: sidebar + content area."""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from axon.api import api_get
from axon.tui.views.mining import BackFromMining, MiningView
from axon.tui.views.settings import SettingsView
from axon.tui.views.task_detail import BackToList, StartMining, TaskDetailView
from axon.tui.views.task_list import MineTaskRequested, TaskListView, ViewTaskRequested
from axon.tui.views.wallet import WalletView
from axon.tui.widgets.sidebar import MenuSelected, Sidebar


class MainScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("m", "mine_best", "Mine best", show=True),
    ]

    def __init__(self):
        super().__init__()
        self._current = "tasks"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Sidebar(id="sidebar")
        with Vertical(id="content-area"):
            yield Static("Loading...", id="loading")
        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self):
        self.query_one("#sidebar", Sidebar).set_active("tasks")
        self._navigate("tasks")
        self.query_one("#sidebar").focus()

    def _switch_view(self, view, menu_id: str = ""):
        content = self.query_one("#content-area")
        for child in list(content.children):
            child.remove()
        content.mount(view)
        if menu_id:
            self.query_one("#sidebar", Sidebar).set_active(menu_id)
            self._current = menu_id

    def _navigate(self, menu_id: str):
        try:
            if menu_id == "tasks":
                tasks = api_get("/api/tasks?task_status=all", auth=False)
                # Open tasks first (sorted by pool desc), then completed/closed
                open_tasks = sorted(
                    [t for t in tasks if t.get("status") == "open"],
                    key=lambda t: t.get("pool_balance", 0), reverse=True,
                )
                other_tasks = [t for t in tasks if t.get("status") != "open"]
                tasks = open_tasks + other_tasks
                open_count = len(open_tasks)
                self._switch_view(TaskListView(tasks), "tasks")
                self.query_one("#status-bar", Static).update(f"{open_count} open / {len(tasks)} total")
            elif menu_id == "mining":
                self._switch_view(Static("[dim]Select a task first, then press m to mine[/]"), "mining")
            elif menu_id == "wallet":
                self._switch_view(WalletView(), "wallet")
            elif menu_id == "config":
                self._switch_view(SettingsView(), "config")
        except Exception as e:
            self._switch_view(Static(f"[red]Error: {e}[/]"), menu_id)

    # --- Message handlers ---

    def on_menu_selected(self, msg: MenuSelected):
        self._navigate(msg.menu_id)

    def on_view_task_requested(self, msg: ViewTaskRequested):
        try:
            task = api_get(f"/api/tasks/{msg.task_id}", auth=False)
            self._switch_view(TaskDetailView(task))
        except Exception as e:
            self.query_one("#status-bar", Static).update(f"Error: {e}")

    def on_mine_task_requested(self, msg: MineTaskRequested):
        self._start_mining(msg.task_id)

    def on_start_mining(self, msg: StartMining):
        self._start_mining(msg.task_id)

    def on_back_to_list(self, msg: BackToList):
        self._navigate("tasks")

    def on_back_from_mining(self, msg: BackFromMining):
        self._navigate("tasks")

    def _start_mining(self, task_id: str):
        self.query_one("#sidebar", Sidebar).set_active("mining")
        self._current = "mining"
        self._switch_view(MiningView(task_id))
        self.query_one("#status-bar", Static).update(f"Mining {task_id[:8]}...")

    # --- Key bindings ---

    def action_refresh(self):
        self._navigate(self._current)

    def action_mine_best(self):
        """Auto-pick highest pool task and start mining."""
        try:
            tasks = api_get("/api/tasks?task_status=open", auth=False)
            tasks.sort(key=lambda t: t.get("pool_balance", 0), reverse=True)
            if tasks:
                self._start_mining(tasks[0]["id"])
            else:
                self.query_one("#status-bar", Static).update("No open tasks")
        except Exception as e:
            self.query_one("#status-bar", Static).update(f"Error: {e}")
