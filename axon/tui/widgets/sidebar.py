"""Sidebar navigation widget — arrow-key driven."""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class MenuSelected(Message):
    def __init__(self, menu_id: str):
        super().__init__()
        self.menu_id = menu_id


class MenuItem(Static):
    active = reactive(False)
    highlighted = reactive(False)

    def __init__(self, label: str, menu_id: str):
        super().__init__(f"  {label}", classes="menu-item")
        self.menu_id = menu_id
        self._label = label
        self._count = 0

    def _refresh_text(self):
        prefix = "❯ " if self.highlighted else "  "
        suffix = f" ({self._count})" if self._count > 0 else ""
        self.update(f"{prefix}{self._label}{suffix}")

    def update_count(self, count: int):
        self._count = count
        self._refresh_text()

    def watch_active(self, value: bool):
        self.set_class(value, "active")

    def watch_highlighted(self, value: bool):
        self._refresh_text()

    def on_click(self):
        self.post_message(MenuSelected(self.menu_id))


class Sidebar(Widget):
    can_focus = True
    cursor = reactive(0)

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("enter", "select", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("ψ Axon", classes="brand")
        yield MenuItem("Tasks", "tasks")
        yield MenuItem("Mining", "mining")
        yield MenuItem("Wallet", "wallet")
        yield MenuItem("Config", "config")

    def on_mount(self):
        self._update_highlight()

    def watch_cursor(self, value: int):
        self._update_highlight()

    def _update_highlight(self):
        items = list(self.query(MenuItem))
        for i, item in enumerate(items):
            item.highlighted = i == self.cursor

    def action_cursor_up(self):
        if self.cursor > 0:
            self.cursor -= 1

    def action_cursor_down(self):
        items = list(self.query(MenuItem))
        if self.cursor < len(items) - 1:
            self.cursor += 1

    def action_select(self):
        items = list(self.query(MenuItem))
        if 0 <= self.cursor < len(items):
            self.post_message(MenuSelected(items[self.cursor].menu_id))

    def set_active(self, menu_id: str):
        items = list(self.query(MenuItem))
        for i, item in enumerate(items):
            is_active = item.menu_id == menu_id
            item.active = is_active
            if is_active:
                self.cursor = i

    def update_counts(self, tasks: int = 0, mining: int = 0, wallet: int = 0):
        items = list(self.query(MenuItem))
        if len(items) >= 3:
            items[0].update_count(tasks)
