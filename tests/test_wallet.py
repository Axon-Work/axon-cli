"""Tests for wallet module — generate, save, load, sign."""
import json
from unittest.mock import patch

from eth_account import Account
from eth_account.messages import encode_defunct

from axon.wallet import generate_wallet, save_wallet, load_wallet, sign_message, get_address


def test_generate_wallet_format():
    wallet = generate_wallet()
    assert "address" in wallet
    assert "private_key" in wallet
    assert wallet["address"].startswith("0x")
    assert len(wallet["address"]) == 42
    assert len(wallet["private_key"]) > 0


def test_save_and_load_roundtrip(tmp_path):
    wallet_file = tmp_path / "wallet.json"
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        wallet = generate_wallet()
        save_wallet(wallet)
        loaded = load_wallet()
        assert loaded["address"] == wallet["address"]
        assert loaded["private_key"] == wallet["private_key"]


def test_load_nonexistent(tmp_path):
    wallet_file = tmp_path / "nonexistent" / "wallet.json"
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        assert load_wallet() is None


def test_load_corrupt(tmp_path):
    wallet_file = tmp_path / "wallet.json"
    wallet_file.write_text("not json at all")
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        assert load_wallet() is None


def test_save_permissions(tmp_path):
    wallet_file = tmp_path / "wallet.json"
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        save_wallet({"address": "0x123", "private_key": "abc"})
        mode = wallet_file.stat().st_mode & 0o777
        assert mode == 0o600


def test_sign_message_and_verify():
    wallet = generate_wallet()
    message_text = "Sign in to Axon: test-nonce-123"
    sig_hex = sign_message(message_text, wallet["private_key"])

    # Verify signature recovers the correct address
    msg = encode_defunct(text=message_text)
    recovered = Account.recover_message(msg, signature=bytes.fromhex(sig_hex))
    assert recovered.lower() == wallet["address"].lower()


def test_get_address_with_wallet(tmp_path):
    wallet_file = tmp_path / "wallet.json"
    wallet = generate_wallet()
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        save_wallet(wallet)
        addr = get_address()
        assert addr == wallet["address"]


def test_get_address_no_wallet(tmp_path):
    wallet_file = tmp_path / "nonexistent" / "wallet.json"
    with patch("axon.wallet.WALLET_FILE", wallet_file):
        assert get_address() == ""
