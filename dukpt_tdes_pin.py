"""TDES DUKPT (ANSI X9.24-1:2009) PIN block encoding, encryption and decryption.

Scope
-----
* Derivation of the Initial PIN Encryption Key (IPEK / IK) from a BDK + KSN
  -- ANSI X9.24-1:2009, Annex A.2 ("Derivation of the Initial Key").
* Derivation of the current transaction key from the IPEK + KSN
  -- Annex A.3 ("Non-reversible Key Generation Process").
* The *PIN encryption variant* of the transaction key -- Annex A.4.1.
* ISO 9564-1 PIN block formats 0 and 1 ("ISO-0" / "ISO-1").
* TDES-ECB encryption / decryption of the 8-byte PIN block.

The PIN block is exactly one DES block (8 bytes), so ECB and CBC-with-zero-IV
produce identical results; X9.24-1 specifies ECB and that is what is used here.

Everything is verified against the ANSI X9.24-1:2009 Annex A.4 test data --
see test_dukpt_tdes_pin.py.

Note on the two-key TDES used throughout: a 16-byte key K is used as
K1||K2 in EDE mode (encrypt with K1, decrypt with K2, encrypt with K1).
An 8-byte key means single DES.

SECURITY: this is a software reference implementation, intended for
development, test-vector validation and debugging. In production the BDK
never leaves an HSM; do not hold a real BDK in application memory.
"""

from __future__ import annotations

import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, modes

try:  # cryptography >= 43 moved TripleDES out of the supported algorithms
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:  # cryptography < 43
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

__all__ = [
    "derive_ipek",
    "derive_transaction_key",
    "derive_pin_encryption_key",
    "encode_pin_block",
    "decode_pin_block",
    "encrypt_pin_block",
    "decrypt_pin_block",
    "encrypt_pin",
    "decrypt_pin",
]

KSN_LEN = 10  # bytes
KEY_LEN = 16  # bytes (double-length TDES)
BLOCK_LEN = 8  # bytes

# Annex A.2 / A.3: the "key mask" applied to derive the right half of a key.
_KEY_MASK = bytes.fromhex("C0C0C0C000000000C0C0C0C000000000")
# Annex A.4.1: the PIN encryption variant of the transaction key.
_PIN_VARIANT = bytes.fromhex("00000000000000FF00000000000000FF")

_COUNTER_MASK = (1 << 21) - 1  # transaction counter = 21 least significant bits
_MAX_COUNTER_BITS = 10  # a valid counter never has more than 10 bits set


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _des_ecb(key: bytes, block: bytes, encrypt: bool = True) -> bytes:
    """Single ECB operation on one 8-byte block.

    An 8-byte key selects single DES, a 16-byte key selects two-key TDES.
    """
    if len(key) not in (8, 16, 24):
        raise ValueError(f"key must be 8, 16 or 24 bytes, got {len(key)}")
    if len(block) != BLOCK_LEN:
        raise ValueError(f"block must be {BLOCK_LEN} bytes, got {len(block)}")
    cipher = Cipher(TripleDES(key), modes.ECB())
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    return ctx.update(block) + ctx.finalize()


def _as_bytes(value: bytes | bytearray | str, name: str) -> bytes:
    """Accept either raw bytes or a hex string."""
    if isinstance(value, str):
        try:
            return bytes.fromhex(value.replace(" ", ""))
        except ValueError as exc:
            raise ValueError(f"{name} is not valid hex: {value!r}") from exc
    return bytes(value)


def _normalise_ksn(ksn: bytes | str) -> bytes:
    """Return the KSN as 10 bytes, left-padding short KSNs with 0xFF.

    Terminals commonly report the Initial Key Serial Number without the
    leading filler, e.g. "9876543210E00001"; X9.24-1 pads it to 10 bytes
    with 0xFF.
    """
    raw = _as_bytes(ksn, "ksn")
    if len(raw) > KSN_LEN:
        raise ValueError(f"ksn must be at most {KSN_LEN} bytes, got {len(raw)}")
    return b"\xff" * (KSN_LEN - len(raw)) + raw


def _check_key(key: bytes, name: str) -> bytes:
    if len(key) != KEY_LEN:
        raise ValueError(f"{name} must be {KEY_LEN} bytes, got {len(key)}")
    return key


def ksn_counter(ksn: bytes | str) -> int:
    """The 21-bit transaction counter carried in the KSN."""
    return int.from_bytes(_normalise_ksn(ksn), "big") & _COUNTER_MASK


# --------------------------------------------------------------------------
# key derivation -- ANSI X9.24-1:2009 Annex A.2 and A.3
# --------------------------------------------------------------------------


def derive_ipek(bdk: bytes | str, ksn: bytes | str) -> bytes:
    """Derive the Initial PIN Encryption Key (IPEK, a.k.a. IK) -- Annex A.2.

    The KSN's transaction counter is ignored (zeroed), so every KSN from one
    device yields the same IPEK.
    """
    bdk = _check_key(_as_bytes(bdk, "bdk"), "bdk")
    ksn_int = int.from_bytes(_normalise_ksn(ksn), "big")
    # Zero the 21-bit counter, then take the leftmost 8 bytes.
    base = (ksn_int & ~_COUNTER_MASK).to_bytes(KSN_LEN, "big")[:BLOCK_LEN]

    left = _des_ecb(bdk, base)
    right = _des_ecb(_xor(bdk, _KEY_MASK), base)
    return left + right


def _non_reversible_key_generation(key: bytes, ksn_reg: bytes) -> bytes:
    """The Non-reversible Key Generation Process -- Annex A.3.

    `ksn_reg` is the rightmost 8 bytes of the current KSN register.
    """
    # Right half of the new key, from the key as-is.
    cur_right = _xor(_des_ecb(key[:8], _xor(ksn_reg, key[8:])), key[8:])
    # Left half of the new key, from the masked key.
    variant = _xor(key, _KEY_MASK)
    cur_left = _xor(_des_ecb(variant[:8], _xor(ksn_reg, variant[8:])), variant[8:])
    return cur_left + cur_right


def derive_transaction_key(ipek: bytes | str, ksn: bytes | str) -> bytes:
    """Derive the transaction key for `ksn` from the IPEK -- Annex A.3.

    Walks the 21-bit transaction counter from the most significant set bit
    down, applying the non-reversible key generation process once per set bit.
    """
    key = _check_key(_as_bytes(ipek, "ipek"), "ipek")
    ksn_int = int.from_bytes(_normalise_ksn(ksn), "big")
    counter = ksn_int & _COUNTER_MASK
    if bin(counter).count("1") > _MAX_COUNTER_BITS:
        raise ValueError(
            f"invalid KSN: transaction counter {counter} has more than "
            f"{_MAX_COUNTER_BITS} bits set"
        )

    # KSN register with the counter cleared; only its rightmost 8 bytes are used.
    reg = ksn_int & ~_COUNTER_MASK
    for bit in range(20, -1, -1):
        mask = 1 << bit
        if counter & mask:
            reg |= mask
            ksn_reg = reg.to_bytes(KSN_LEN, "big")[KSN_LEN - BLOCK_LEN :]
            key = _non_reversible_key_generation(key, ksn_reg)
    return key


def derive_pin_encryption_key(bdk: bytes | str, ksn: bytes | str) -> bytes:
    """BDK + KSN -> the PIN encryption key for that transaction.

    That is: IPEK -> transaction key -> PIN variant (XOR with
    00000000000000FF00000000000000FF, Annex A.4.1).
    """
    ipek = derive_ipek(bdk, ksn)
    txn_key = derive_transaction_key(ipek, ksn)
    return _xor(txn_key, _PIN_VARIANT)


# --------------------------------------------------------------------------
# PIN blocks -- ISO 9564-1 formats 0 and 1
# --------------------------------------------------------------------------


def _check_pin(pin: str) -> str:
    if not pin.isdigit():
        raise ValueError("pin must contain digits only")
    if not 4 <= len(pin) <= 12:
        raise ValueError(f"pin must be 4..12 digits, got {len(pin)}")
    return pin


def _pan_field(pan: str) -> str:
    """The 12-digit PAN field of an ISO-0 block.

    The 12 rightmost PAN digits *excluding* the check digit, zero-padded.
    """
    if not pan.isdigit():
        raise ValueError("pan must contain digits only")
    if len(pan) < 2:
        raise ValueError("pan is too short")
    return pan[:-1][-12:].rjust(12, "0")


def encode_pin_block(pin: str, pan: str | None = None, fmt: str = "ISO-0") -> bytes:
    """Build a clear 8-byte PIN block.

    ISO-0 (ISO 9564-1 format 0) needs the PAN; the block is
    ``0C PP PP PP FF FF FF FF`` XORed with the zero-padded PAN field, and is
    deterministic for a given PIN/PAN pair.

    ISO-1 (format 1) takes no PAN and pads with random nibbles, so a fresh
    block is produced on every call.
    """
    pin = _check_pin(pin)
    fmt = fmt.upper()

    if fmt == "ISO-0":
        if pan is None:
            raise ValueError("ISO-0 requires a PAN")
        pin_field = f"0{len(pin):X}{pin}".ljust(16, "F")
        pan_field = f"0000{_pan_field(pan)}"
        return _xor(bytes.fromhex(pin_field), bytes.fromhex(pan_field))

    if fmt == "ISO-1":
        # 0x1, PIN length, PIN digits, then random fill to 16 nibbles.
        fill = "".join(f"{secrets.randbelow(16):X}" for _ in range(16 - 2 - len(pin)))
        return bytes.fromhex(f"1{len(pin):X}{pin}{fill}")

    raise ValueError(f"unsupported PIN block format: {fmt!r} (use ISO-0 or ISO-1)")


def decode_pin_block(block: bytes | str, pan: str | None = None, fmt: str = "ISO-0") -> str:
    """Recover the PIN from a clear 8-byte PIN block."""
    block = _as_bytes(block, "block")
    if len(block) != BLOCK_LEN:
        raise ValueError(f"PIN block must be {BLOCK_LEN} bytes, got {len(block)}")
    fmt = fmt.upper()

    if fmt == "ISO-0":
        if pan is None:
            raise ValueError("ISO-0 requires a PAN")
        pan_field = bytes.fromhex(f"0000{_pan_field(pan)}")
        digits = _xor(block, pan_field).hex().upper()
        control = digits[0]
        expected = "0"
    elif fmt == "ISO-1":
        digits = block.hex().upper()
        control = digits[0]
        expected = "1"
    else:
        raise ValueError(f"unsupported PIN block format: {fmt!r} (use ISO-0 or ISO-1)")

    if control != expected:
        raise ValueError(
            f"not a valid {fmt} PIN block: control field is {control}, "
            f"expected {expected} (wrong PAN, wrong key or wrong format?)"
        )
    length = int(digits[1], 16)
    if not 4 <= length <= 12:
        raise ValueError(f"invalid PIN length nibble: {length}")
    pin = digits[2 : 2 + length]
    if not pin.isdigit():
        raise ValueError("decoded PIN contains non-decimal digits")
    return pin


# --------------------------------------------------------------------------
# encryption / decryption
# --------------------------------------------------------------------------


def encrypt_pin_block(pin_key: bytes | str, block: bytes | str) -> bytes:
    """TDES-ECB encrypt a clear 8-byte PIN block under the PIN encryption key."""
    return _des_ecb(_check_key(_as_bytes(pin_key, "pin_key"), "pin_key"),
                    _as_bytes(block, "block"), encrypt=True)


def decrypt_pin_block(pin_key: bytes | str, block: bytes | str) -> bytes:
    """TDES-ECB decrypt an 8-byte encrypted PIN block back to the clear block."""
    return _des_ecb(_check_key(_as_bytes(pin_key, "pin_key"), "pin_key"),
                    _as_bytes(block, "block"), encrypt=False)


# --------------------------------------------------------------------------
# one-call convenience API
# --------------------------------------------------------------------------


def encrypt_pin(
    bdk: bytes | str,
    ksn: bytes | str,
    pin: str,
    pan: str | None = None,
    fmt: str = "ISO-0",
) -> bytes:
    """BDK + KSN + PIN (+ PAN) -> 8-byte encrypted PIN block.

    This is the terminal side: derive the transaction's PIN key, format the
    PIN block, encrypt it. The KSN travels with the ciphertext.
    """
    pin_key = derive_pin_encryption_key(bdk, ksn)
    return encrypt_pin_block(pin_key, encode_pin_block(pin, pan, fmt))


def decrypt_pin(
    bdk: bytes | str,
    ksn: bytes | str,
    encrypted_block: bytes | str,
    pan: str | None = None,
    fmt: str = "ISO-0",
) -> str:
    """BDK + KSN + encrypted PIN block (+ PAN) -> clear PIN.

    This is the host side: the received KSN reproduces the same PIN key.
    """
    pin_key = derive_pin_encryption_key(bdk, ksn)
    return decode_pin_block(decrypt_pin_block(pin_key, encrypted_block), pan, fmt)


if __name__ == "__main__":  # pragma: no cover - demo
    # ANSI X9.24-1:2009 Annex A.4 test data.
    BDK = "0123456789ABCDEFFEDCBA9876543210"
    KSN = "FFFF9876543210E00001"
    PIN, PAN = "1234", "4012345678909"

    print(f"BDK                  {BDK}")
    print(f"KSN                  {KSN}")
    print(f"IPEK                 {derive_ipek(BDK, KSN).hex().upper()}")
    print(f"transaction key      {derive_transaction_key(derive_ipek(BDK, KSN), KSN).hex().upper()}")
    print(f"PIN encryption key   {derive_pin_encryption_key(BDK, KSN).hex().upper()}")

    for fmt in ("ISO-0", "ISO-1"):
        pan = PAN if fmt == "ISO-0" else None
        clear = encode_pin_block(PIN, pan, fmt)
        enc = encrypt_pin(BDK, KSN, PIN, pan, fmt)
        back = decrypt_pin(BDK, KSN, enc, pan, fmt)
        print(f"\n{fmt}")
        print(f"  clear PIN block    {clear.hex().upper()}")
        print(f"  encrypted block    {enc.hex().upper()}")
        print(f"  decrypted PIN      {back}  ({'OK' if back == PIN else 'MISMATCH'})")
