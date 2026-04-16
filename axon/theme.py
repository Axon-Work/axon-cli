"""Axon CRT/cyberpunk theme — all colors, box styles, and semantic markup."""
from rich.box import DOUBLE, DOUBLE_EDGE
from rich.console import Console
from rich.theme import Theme

GOLD = "gold1"
CYAN = "cyan"
GREEN = "green"
RED = "red"
YELLOW = "yellow"
DIM = "dim"

PRIMARY_BOX = DOUBLE        # panels
TABLE_BOX = DOUBLE_EDGE     # tables

AXON_THEME = Theme({
    "brand":           f"bold {GOLD}",
    "brand.symbol":    f"{GOLD}",
    "money":           f"{GREEN}",
    "money.bold":      f"bold {GREEN}",
    "address":         f"{CYAN}",
    "accent":          f"{CYAN}",
    "secondary":       f"{DIM}",
    "success":         f"{GREEN}",
    "error":           f"{RED}",
    "warning":         f"{YELLOW}",
    "command":         f"bold {GREEN}",
    "header":          f"bold {GOLD}",
    "result.complete": f"bold {GREEN}",
    "result.improved": f"{GREEN}",
    "result.error":    f"{RED}",
    "result.warning":  f"{YELLOW}",
    "result.neutral":  f"{DIM}",
})

console = Console(theme=AXON_THEME)

STATUS_DOTS = {
    "open":      f"[{GREEN}]\u25cf[/]",
    "completed": f"[{CYAN}]\u25cf[/]",
    "closed":    f"[{RED}]\u25cf[/]",
}


def status_dot(status: str) -> str:
    return STATUS_DOTS.get(status, f"[{DIM}]\u25cf[/]")


def branded_title(text: str) -> str:
    return f"[brand.symbol]\u03a8[/] [brand]{text}[/]"
