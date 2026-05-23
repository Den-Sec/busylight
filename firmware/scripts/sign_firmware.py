"""Sign a BusyLight firmware build with the project's RSA private key.

Usage:

    python sign_firmware.py path/to/firmware.bin [-o path/to/firmware.bin.sig]

Reads the private key from firmware/scripts/private_key.pem (generated
by gen_signing_key.py). Computes SHA-256 of the binary, signs the
digest with PKCS#1 v1.5 + SHA-256, and writes the 256-byte signature
to a sibling .sig file (or the path passed via -o).

Upload the .sig together with the .bin from the web UI: the OTA
handler decodes the .sig from the X-Firmware-Signature header and
refuses any image whose SHA-256 does not match what was signed.

Requires the `cryptography` Python package:

    pip install cryptography
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:
    print(
        "ERROR: the 'cryptography' Python package is required.\n"
        "       pip install cryptography",
        file=sys.stderr,
    )
    raise SystemExit(2)


HERE = Path(__file__).resolve().parent
DEFAULT_KEY = HERE / "private_key.pem"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sign_firmware")
    parser.add_argument("firmware", type=Path, help="The .bin to sign.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Where to write the signature. Default: <firmware>.sig",
    )
    parser.add_argument(
        "-k",
        "--key",
        type=Path,
        default=DEFAULT_KEY,
        help=f"Private key PEM. Default: {DEFAULT_KEY}",
    )
    args = parser.parse_args(argv)

    if not args.key.exists():
        print(
            f"ERROR: signing key {args.key} not found.\n"
            f"       Run gen_signing_key.py first.",
            file=sys.stderr,
        )
        return 1
    if not args.firmware.exists():
        print(f"ERROR: firmware {args.firmware} not found.", file=sys.stderr)
        return 1

    key = serialization.load_pem_private_key(
        args.key.read_bytes(), password=None
    )

    data = args.firmware.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    sig = key.sign(
        data,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    out_path = args.output or args.firmware.with_suffix(
        args.firmware.suffix + ".sig"
    )
    out_path.write_bytes(sig)

    print(f"  SHA-256:    {sha}")
    print(f"  Signature:  {len(sig)} bytes -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
