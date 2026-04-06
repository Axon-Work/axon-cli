"""Settings view — config display + model switching."""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static
from textual import work

from axon.config import load_config, save_config
from axon.providers import fetch_models


class SettingsView(VerticalScroll):
    BINDINGS = [
        Binding("m", "change_model", "Change model", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static("", id="settings-content")
        yield Static("", id="settings-models")

    def on_mount(self):
        self._render_config()

    def _render_config(self):
        config = load_config()
        logged_in = bool(config.get("auth_token"))
        auth_status = "[green]logged in[/]" if logged_in else "[red]not logged in[/]"

        keys = config.get("api_keys", {})
        key_lines = []
        for provider in ["anthropic", "openai", "deepseek"]:
            key = keys.get(provider, "")
            status = f"[green]****{key[-8:]}[/]" if key else "[red]not set[/]"
            key_lines.append(f"    {provider}: {status}")

        text = "\n".join([
            "[bold gold1]ψ Settings[/]",
            "",
            f"  [bold]Server[/]     [cyan]{config['server_url']}[/]",
            f"  [bold]Model[/]      [cyan]{config['default_model']}[/]",
            f"  [bold]API Base[/]   [cyan]{config.get('api_base') or '(default)'}[/]",
            f"  [bold]Auth[/]       {auth_status}",
            "",
            "  [bold]API Keys[/]",
        ] + key_lines + [
            "",
            "  [dim]m: change model[/]",
        ])
        self.query_one("#settings-content", Static).update(text)

    def action_change_model(self):
        """Fetch models and show picker."""
        self.query_one("#settings-models", Static).update("  [dim]Fetching models...[/]")
        self._load_models()

    @work(thread=True)
    def _load_models(self):
        config = load_config()
        current = config.get("default_model", "")
        provider = current.split("/")[0] if "/" in current else ""
        keys = config.get("api_keys", {})
        api_key = keys.get(provider, "")
        api_base = config.get("api_base", "")

        models = []
        if api_key or provider == "ollama":
            models = fetch_models(provider, api_key, api_base)

        self.app.call_from_thread(self._show_model_picker, models, current)

    def _show_model_picker(self, models: list[dict], current: str):
        if not models:
            self.query_one("#settings-models", Static).update(
                "  [yellow]No models found. Set API key first via axon onboard.[/]"
            )
            return

        self._models = models
        lines = ["\n  [bold]Select model[/] (number + Enter):\n"]
        for i, m in enumerate(models[:20], 1):
            marker = " [green]◀[/]" if m["value"] == current else ""
            lines.append(f"    [cyan]{i:>2}[/]  {m['label']}{marker}")
        lines.append("\n  [dim]Type number and press Enter:[/]")
        self.query_one("#settings-models", Static).update("\n".join(lines))

        # Enable number input mode
        self._picking_model = True
        self._model_input = ""

    def on_key(self, event):
        if not getattr(self, "_picking_model", False):
            return

        if event.key == "escape":
            self._picking_model = False
            self.query_one("#settings-models", Static).update("")
            event.prevent_default()
            return

        if event.key == "enter" and self._model_input:
            try:
                idx = int(self._model_input) - 1
                if 0 <= idx < len(self._models):
                    chosen = self._models[idx]["value"]
                    save_config({"default_model": chosen})
                    self._picking_model = False
                    self.query_one("#settings-models", Static).update(
                        f"  [green]✓ Model: {chosen}[/]"
                    )
                    self._render_config()
            except ValueError:
                pass
            self._model_input = ""
            event.prevent_default()
            return

        if event.character and event.character.isdigit():
            self._model_input += event.character
            event.prevent_default()
