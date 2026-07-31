"""Verification of dukpt_tdes_pin against the ANSI X9.24-1:2009 Annex A.4 test data.

The 21 vectors below are the "initial sequence" from Annex A.4.2 of the
standard: BDK 0123456789ABCDEFFEDCBA9876543210, initial KSN
FFFF9876543210E00000, PIN 1234, PAN 4012345678909, ISO-0 PIN block.

Run with:  python3 -m pytest test_dukpt_tdes_pin.py
       or: python3 test_dukpt_tdes_pin.py
"""

from __future__ import annotations

import pytest

from dukpt_tdes_pin import (
    decode_pin_block,
    decrypt_pin,
    derive_ipek,
    derive_pin_encryption_key,
    derive_transaction_key,
    encode_pin_block,
    encrypt_pin,
    ksn_counter,
)

BDK = "0123456789ABCDEFFEDCBA9876543210"
INITIAL_KSN = "FFFF9876543210E00000"
IPEK = "6AC292FAA1315B4D858AB3A3D7D5933A"
PIN = "1234"
PAN = "4012345678909"
CLEAR_PIN_BLOCK_ISO0 = "041274EDCBA9876F"

# (KSN, transaction key, encrypted ISO-0 PIN block) -- Annex A.4.2
SEQUENCE = [
    ("FFFF9876543210E00001", "042666B49184CFA368DE9628D0397BC9", "1B9C1845EB993A7A"),
    ("FFFF9876543210E00002", "C46551CEF9FD24B0AA9AD834130D3BC7", "10A01C8D02C69107"),
    ("FFFF9876543210E00003", "0DF3D9422ACA56E547676D07AD6BADFA", "18DC07B94797B466"),
    ("FFFF9876543210E00004", "279C0F6AEED0BE652B2C733E1383AE91", "0BC79509D5645DF7"),
    ("FFFF9876543210E00005", "5F8DC6D2C845C125508DDC048093B83F", "5BC0AF22AD87B327"),
    ("FFFF9876543210E00006", "5E415CB0BAF9F03CD0C14B63FB62FF43", "A16DF70AE36158D8"),
    ("FFFF9876543210E00007", "0C8F780B7C8B49D0AE84A9EB2A6CE660", "27711C16CB257F8E"),
    ("FFFF9876543210E00008", "27F66D5244FF62E1AA6F6120EDEB4280", "50E55547A5027551"),
    ("FFFF9876543210E00009", "27E31064FDC565698900E2057F658E7E", "536CF7F678ACFC8D"),
    ("FFFF9876543210E0000A", "6CF2500A22507C7CC776CEADC1E33014", "EDABBA23221833FE"),
    ("FFFF9876543210E0000B", "3E8260BA04B2D620C01482B3819A18B7", "2328981C57B4BDBA"),
    ("FFFF9876543210E0000C", "B716E1E11CF53D80726CAEE75C3A624F", "038D03CC926CF286"),
    ("FFFF9876543210E0000D", "E072EDF95340535FB6C581C58FBF2533", "6C8AA97088B62C68"),
    ("FFFF9876543210E0000E", "A80046087F5B8F245AAD95E18429084F", "F17C9E1D72CD4950"),
    ("FFFF9876543210E0000F", "93DD5B956C4878472E453AAEFD32A5AA", "B170F6E7F7F2F64A"),
    ("FFFF9876543210E00010", "59598DCBD9BD94C094165CE453585F57", "D5D9638559EF53D6"),
    ("FFFF9876543210E00011", "2B5F01F4F0CC05EA639D523231BF1BA2", "D544F8CDD292C863"),
    ("FFFF9876543210E00012", "9CF640F279C2AEE615F725EEEAC2CBAF", "7A21BD10F36DC41D"),
    ("FFFF9876543210E00013", "C3DF489FDF1153B4F03DE97C27DC4C2F", "78649BD17D0DFA60"),
    ("FFFF9876543210E00014", "658488507721B3F14737FA93F923CBD2", "7E7E16EA0C31AD56"),
    ("FFFF9876543210E00015", "E161D1956A61F6D2F37AFD7F9CC3699A", "72105C22EBC791E6"),
]


def test_ipek_derivation():
    """Annex A.2 -- the IPEK is independent of the transaction counter."""
    assert derive_ipek(BDK, INITIAL_KSN).hex().upper() == IPEK
    # any KSN of the same device derives the same IPEK
    assert derive_ipek(BDK, "FFFF9876543210E00015").hex().upper() == IPEK
    # a short KSN is left-padded with 0xFF
    assert derive_ipek(BDK, "9876543210E00001").hex().upper() == IPEK


def test_clear_iso0_pin_block():
    assert encode_pin_block(PIN, PAN, "ISO-0").hex().upper() == CLEAR_PIN_BLOCK_ISO0
    assert decode_pin_block(CLEAR_PIN_BLOCK_ISO0, PAN, "ISO-0") == PIN


@pytest.mark.parametrize("ksn,txn_key,encrypted", SEQUENCE)
def test_annex_a4_sequence(ksn, txn_key, encrypted):
    """Annex A.3 / A.4 -- transaction key, PIN variant, encrypt and decrypt."""
    assert derive_transaction_key(IPEK, ksn).hex().upper() == txn_key

    # the PIN key is the transaction key XOR 00000000000000FF00000000000000FF
    pin_key = derive_pin_encryption_key(BDK, ksn)
    expected_pin_key = (int(txn_key, 16) ^ 0x00000000000000FF00000000000000FF)
    assert pin_key.hex().upper() == f"{expected_pin_key:032X}"

    assert encrypt_pin(BDK, ksn, PIN, PAN, "ISO-0").hex().upper() == encrypted
    assert decrypt_pin(BDK, ksn, encrypted, PAN, "ISO-0") == PIN


def test_ksn_counter():
    assert ksn_counter("FFFF9876543210E00001") == 1
    assert ksn_counter("FFFF9876543210E00015") == 0x15
    assert ksn_counter(INITIAL_KSN) == 0


@pytest.mark.parametrize("pin", ["1234", "123456", "012345678901"])
@pytest.mark.parametrize("fmt", ["ISO-0", "ISO-1"])
def test_roundtrip(pin, fmt):
    ksn = "FFFF9876543210E00007"
    pan = PAN if fmt == "ISO-0" else None
    encrypted = encrypt_pin(BDK, ksn, pin, pan, fmt)
    assert len(encrypted) == 8
    assert decrypt_pin(BDK, ksn, encrypted, pan, fmt) == pin


def test_iso1_is_randomised():
    """ISO-1 pads with random nibbles, so ciphertext differs per call."""
    blocks = {encrypt_pin(BDK, "FFFF9876543210E00003", PIN, fmt="ISO-1") for _ in range(20)}
    assert len(blocks) > 1
    for block in blocks:
        assert decrypt_pin(BDK, "FFFF9876543210E00003", block, fmt="ISO-1") == PIN


def test_iso0_wrong_pan_yields_wrong_pin_silently():
    """ISO-0 carries no integrity check: the wrong PAN gives the wrong PIN.

    The PAN field's leading nibbles are zero, so the control and length
    nibbles survive a PAN mismatch untouched -- decoding succeeds and returns
    garbage. The host must use the PAN that the terminal actually used.
    """
    encrypted = encrypt_pin(BDK, "FFFF9876543210E00001", PIN, PAN, "ISO-0")
    wrong = decrypt_pin(BDK, "FFFF9876543210E00001", encrypted, "5555444433332226", "ISO-0")
    assert wrong != PIN


def test_wrong_ksn_does_not_recover_the_pin():
    """A different KSN derives a different key, so the PIN is not recovered."""
    encrypted = encrypt_pin(BDK, "FFFF9876543210E00001", PIN, PAN, "ISO-0")
    try:
        assert decrypt_pin(BDK, "FFFF9876543210E00002", encrypted, PAN, "ISO-0") != PIN
    except ValueError:
        pass  # garbage plaintext failed the control/length/digit checks


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (dict(pin="123", pan=PAN, fmt="ISO-0"), "4..12 digits"),
        (dict(pin="12a4", pan=PAN, fmt="ISO-0"), "digits only"),
        (dict(pin=PIN, pan=None, fmt="ISO-0"), "requires a PAN"),
        (dict(pin=PIN, pan=PAN, fmt="ISO-3"), "unsupported PIN block format"),
    ],
)
def test_input_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        encode_pin_block(**kwargs)


def test_invalid_ksn_counter_rejected():
    """A counter with more than 10 bits set cannot come from a real device."""
    with pytest.raises(ValueError, match="more than 10 bits"):
        derive_transaction_key(IPEK, "FFFF9876543210E1FFFF")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
