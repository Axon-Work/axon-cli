"""ETH wallet — generate, load, sign."""
import json

from eth_account import Account
from eth_account.messages import encode_defunct

from axon._fs import atomic_write_json
from axon.config import AXON_HOME

WALLET_FILE = AXON_HOME / "wallet.json"


def generate_wallet() -> dict:
    """Generate a new ETH wallet. Returns {address, private_key}."""
    acct = Account.create()
    return {"address": acct.address, "private_key": acct.key.hex()}


def save_wallet(wallet: dict) -> None:
    """Save wallet atomically with 0o600 permissions (owner-only read/write)."""
    atomic_write_json(WALLET_FILE, wallet, mode=0o600)


def load_wallet() -> dict | None:
    """Load wallet from disk. Returns {address, private_key} or None."""
    if not WALLET_FILE.exists():
        return None
    try:
        return json.loads(WALLET_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def sign_message(message: str, private_key: str) -> str:
    """Sign a message with private key. Returns hex signature."""
    msg = encode_defunct(text=message)
    signed = Account.sign_message(msg, private_key=private_key)
    return signed.signature.hex()


def get_address() -> str:
    """Get wallet address or empty string."""
    wallet = load_wallet()
    return wallet["address"] if wallet else ""
