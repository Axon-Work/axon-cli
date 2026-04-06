"""Tests for auth module — nonce, signature verification, JWT."""
import uuid
from axon_server.auth import generate_nonce, verify_signature, create_token


def test_generate_nonce():
    n1 = generate_nonce()
    n2 = generate_nonce()
    assert isinstance(n1, str)
    assert len(n1) == 64  # 32 bytes hex
    assert n1 != n2


def test_verify_signature_valid():
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.create()
    nonce = generate_nonce()
    message = encode_defunct(text=f"Sign in to Axon: {nonce}")
    sig = acct.sign_message(message)
    assert verify_signature(acct.address, nonce, sig.signature.hex())


def test_verify_signature_wrong_nonce():
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.create()
    nonce = generate_nonce()
    message = encode_defunct(text=f"Sign in to Axon: {nonce}")
    sig = acct.sign_message(message)
    assert not verify_signature(acct.address, "wrong_nonce", sig.signature.hex())


def test_verify_signature_wrong_address():
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.create()
    other = Account.create()
    nonce = generate_nonce()
    message = encode_defunct(text=f"Sign in to Axon: {nonce}")
    sig = acct.sign_message(message)
    assert not verify_signature(other.address, nonce, sig.signature.hex())


def test_verify_signature_garbage():
    assert not verify_signature("0x0000", "nonce", "garbage")


def test_create_token():
    user_id = uuid.uuid4()
    token = create_token(user_id)
    assert isinstance(token, str)
    assert len(token) > 20


def test_create_token_different_users():
    t1 = create_token(uuid.uuid4())
    t2 = create_token(uuid.uuid4())
    assert t1 != t2
