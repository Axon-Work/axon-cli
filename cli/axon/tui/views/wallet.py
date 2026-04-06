"""Wallet view — address, on-chain + platform balances."""
import httpx
from textual import work
from textual.widgets import Static

from axon.api import api_get
from axon.wallet import WALLET_FILE, load_wallet

# Ethereum mainnet ERC-20 contracts
_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
_USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
_RPC = "https://eth.llamarpc.com"
_BALANCE_OF = "0x70a08231"  # balanceOf(address) selector


def _eth_rpc(method: str, params: list) -> str | None:
    try:
        resp = httpx.post(_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        }, timeout=8)
        return resp.json().get("result")
    except Exception:
        return None


def _fetch_eth_balance(address: str) -> float:
    result = _eth_rpc("eth_getBalance", [address, "latest"])
    if result:
        return int(result, 16) / 1e18
    return 0.0


def _fetch_erc20_balance(address: str, contract: str, decimals: int) -> float:
    addr_padded = "0" * 24 + address[2:].lower()
    data = _BALANCE_OF + addr_padded
    result = _eth_rpc("eth_call", [{"to": contract, "data": data}, "latest"])
    if result and result != "0x":
        return int(result, 16) / (10 ** decimals)
    return 0.0


def _format(address: str, *, eth: str, axn: str, usdc: str, usdt: str) -> str:
    return "\n".join([
        "[bold gold1]ψ Wallet[/]",
        "",
        f"  [bold]Address[/]      [cyan]{address}[/]",
        f"  [bold]Key file[/]     [dim]{WALLET_FILE}[/]",
        "",
        "  [bold]Balances[/]",
        "  ─────────────────────────────────",
        f"    $ETH     [bold]{eth:>14}[/]",
        f"    $AXN     [bold green]{axn:>14}[/]",
        f"    $USDC    [bold]{usdc:>14}[/]",
        f"    $USDT    [bold]{usdt:>14}[/]",
    ])


class WalletView(Static):
    """Wallet info panel — extends Static directly for reliable rendering."""

    def on_mount(self):
        wallet = load_wallet()
        if not wallet:
            self.update("[bold gold1]ψ Wallet[/]\n\n  [red]No wallet found. Run: axon onboard[/]")
            return
        self._address = wallet["address"]
        self.update(_format(
            self._address,
            eth="[dim]loading...[/]",
            axn="[dim]loading...[/]",
            usdc="[dim]loading...[/]",
            usdt="[dim]loading...[/]",
        ))
        self._fetch_balances()

    @work(thread=True)
    def _fetch_balances(self):
        axn = 0
        try:
            me = api_get("/api/auth/me")
            axn = me.get("balance", 0)
        except Exception:
            pass

        eth = _fetch_eth_balance(self._address)
        usdc = _fetch_erc20_balance(self._address, _USDC, 6)
        usdt = _fetch_erc20_balance(self._address, _USDT, 6)

        self.app.call_from_thread(
            self.update,
            _format(
                self._address,
                eth=f"{eth:.6f}",
                axn=f"{axn:,}",
                usdc=f"{usdc:.2f}",
                usdt=f"{usdt:.2f}",
            ),
        )
