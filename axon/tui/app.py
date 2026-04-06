"""Axon TUI — interactive terminal mining interface."""
import logging

from textual.app import App
from textual.binding import Binding

from axon.log import setup_logging
from axon.tui.screens.main import MainScreen

setup_logging()
log = logging.getLogger("axon.tui")


class AxonApp(App):
    TITLE = "Axon"
    SUB_TITLE = "Proof of Useful Work Mining"
    CSS_PATH = "css/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+o", "toggle_debug", "Response", show=True),
    ]

    def on_mount(self):
        self.push_screen(MainScreen())

    def on_worker_state_changed(self, event):
        """Log worker errors that Textual would otherwise swallow."""
        if event.worker.error:
            log.error("Worker %s failed: %s", event.worker.name, event.worker.error, exc_info=event.worker.error)


def run_tui():
    app = AxonApp()
    app.run()
