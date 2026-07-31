# TDES DUKPT PIN block encryption (ANSI X9.24-1:2009)

A small, dependency-light reference implementation of the PIN path of TDES
DUKPT: derive the transaction's PIN encryption key from a BDK + KSN, format the
PIN into an ISO-0 or ISO-1 PIN block, encrypt it with TDES-ECB, and decrypt it
again.

Every step is verified against the **ANSI X9.24-1:2009 Annex A.4** test data
(all 21 vectors of the A.4.2 initial sequence).

```
dukpt_tdes_pin.py        the implementation
test_dukpt_tdes_pin.py   the X9.24-1:2009 Annex A.4 vectors + round-trip tests
```

## Usage

```python
from dukpt_tdes_pin import encrypt_pin, decrypt_pin

BDK = "0123456789ABCDEFFEDCBA9876543210"   # your PIN BDK (in an HSM, in production)
KSN = "FFFF9876543210E00001"               # comes from the terminal

# terminal side
encrypted = encrypt_pin(BDK, KSN, pin="1234", pan="4012345678909", fmt="ISO-0")
encrypted.hex().upper()          # '1B9C1845EB993A7A'

# host side -- the KSN reproduces the same key
decrypt_pin(BDK, KSN, encrypted, pan="4012345678909", fmt="ISO-0")   # '1234'
```

ISO-1 takes no PAN:

```python
encrypted = encrypt_pin(BDK, KSN, pin="1234", fmt="ISO-1")
decrypt_pin(BDK, KSN, encrypted, fmt="ISO-1")                        # '1234'
```

The lower-level steps are exposed separately when you need to inspect them:

```python
from dukpt_tdes_pin import (
    derive_ipek, derive_transaction_key, derive_pin_encryption_key,
    encode_pin_block, decode_pin_block, encrypt_pin_block, decrypt_pin_block,
)

ipek     = derive_ipek(BDK, KSN)                     # 6AC292FAA1315B4D858AB3A3D7D5933A
txn_key  = derive_transaction_key(ipek, KSN)         # 042666B49184CFA368DE9628D0397BC9
pin_key  = derive_pin_encryption_key(BDK, KSN)       # 042666B49184CF5C68DE9628D0397B36
block    = encode_pin_block("1234", "4012345678909") # 041274EDCBA9876F
```

Only `cryptography` is required (`pip install cryptography`); `pytest` to run
the tests.

```
python3 dukpt_tdes_pin.py                    # demo against the X9.24 test data
python3 -m pytest test_dukpt_tdes_pin.py -q  # 38 tests
```

## How the pieces fit together

1. **IPEK** (Annex A.2) — the KSN's 21-bit transaction counter is zeroed and the
   leftmost 8 bytes are TDES-encrypted twice: once under the BDK, once under
   `BDK XOR C0C0C0C000000000C0C0C0C000000000`. The halves concatenate to the
   16-byte Initial PIN Encryption Key. It does not depend on the counter, so
   every KSN from one device gives the same IPEK.
2. **Transaction key** (Annex A.3) — the counter is walked from its most
   significant set bit downwards; each set bit runs one *non-reversible key
   generation process* over the current key. That one-way step is what stops a
   compromised transaction key from revealing earlier ones.
3. **PIN encryption key** (Annex A.4.1) — the transaction key XOR
   `00000000000000FF00000000000000FF`. This variant is what actually encrypts
   the PIN block; forgetting it is the single most common reason an
   implementation matches nothing.
4. **PIN block** — ISO 9564-1 format 0 or 1, 8 bytes.
5. **Encryption** — TDES-EDE, ECB, one block.

## Things worth knowing before you ship this

- **The PIN variant is mandatory.** If your ciphertext is wrong but your
  transaction key matches the vectors, step 3 is what you're missing.
- **ECB vs CBC is moot here.** The PIN block is exactly one DES block, so
  ECB and CBC-with-zero-IV are identical. X9.24-1 specifies ECB.
- **ISO-0 is deterministic and unauthenticated.** The same PIN+PAN under the
  same key always gives the same ciphertext, and a wrong PAN at the host
  silently produces a wrong PIN rather than an error — the PAN field's leading
  nibbles are zero, so the control and length nibbles survive a PAN mismatch
  untouched (there's a test covering exactly this). The host must use the PAN
  the terminal used. ISO-1 randomises instead, but carries no PAN binding at
  all, which is why ISO-0 is the norm for card-present PIN entry and ISO-1 is
  for cases where no PAN is available.
- **Counter sanity.** A real DUKPT counter never has more than 10 of its 21
  bits set; the code rejects KSNs that violate this.
- **Key separation.** You already have a separate BDK for PINs, which is
  correct — never derive PIN keys and data-encryption keys from the same BDK.
- **HSMs.** In production the BDK never leaves the HSM. Treat this code as a
  development, test-vector and debugging tool, not as the thing that holds your
  live BDK.
- **TDES DUKPT is legacy.** X9.24-1:2009 has been superseded by
  X9.24-3:2017 (AES DUKPT, ISO 9564 format 4 PIN blocks). If you're building
  something new, check the current PCI PIN Security Requirements for the
  applicable migration dates before committing to TDES.

## Other current implementations worth knowing

Checked July 2026:

| Project | Language | State | Notes |
|---|---|---|---|
| [openemv/dukpt](https://github.com/openemv/dukpt) | C11 | Actively maintained (v1.3.0, Jul 2026) | The best cross-check. TDES (X9.24-1) *and* AES (X9.24-3), separate PIN block library, plus `dukpt-tool` CLI and a Qt UI. Its test suite carries the same Annex A.4 vectors used here. LGPL-2.1 (GPL-3 for the tools). |
| [moov-io/dukpt](https://github.com/moov-io/dukpt) | Go | Maintained (2025) | Clean `EncryptPin`/`DecryptPin` API with ISO-0 support, TDES + AES, plus a CLI and HTTP server. Apache-2.0. |
| [rbonestell/DUKPTCore](https://github.com/rbonestell/DUKPTCore) | C#/.NET Standard 2.0 | Stale (NuGet 1.1.0, 2019) | TDES DUKPT, PIN and data variants. Still functional, but unmaintained — review before adopting. |
| [`dukpt` on PyPI](https://pypi.org/project/dukpt/) | Python | Stale (1.0.1, 2023) | Modelled on IDTech's JavaScript implementation and oriented at the data variant; not recommended for the PIN path. |

`x9.org` publishes the [X9.24-3:2017 test vectors](https://x9.org/wp-content/uploads/2018/03/X9.24-3-2017-Test-Vectors-20180129-1.pdf)
and [Python reference source](https://x9.org/wp-content/uploads/2018/03/X9.24-3-2017-Python-Source-20180129-1.pdf)
free of charge if you move to AES DUKPT.

## Test data

From ANSI X9.24-1:2009 Annex A.4 — the values every implementation should
reproduce:

```
BDK                 0123456789ABCDEFFEDCBA9876543210
initial KSN         FFFF9876543210E00000
IPEK                6AC292FAA1315B4D858AB3A3D7D5933A
PIN / PAN           1234 / 4012345678909
clear ISO-0 block   041274EDCBA9876F

KSN                     transaction key                   encrypted PIN block
FFFF9876543210E00001    042666B49184CFA368DE9628D0397BC9  1B9C1845EB993A7A
FFFF9876543210E00002    C46551CEF9FD24B0AA9AD834130D3BC7  10A01C8D02C69107
FFFF9876543210E00003    0DF3D9422ACA56E547676D07AD6BADFA  18DC07B94797B466
```
