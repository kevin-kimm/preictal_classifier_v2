"""Shared test helpers."""

from pathlib import Path

import numpy as np


def write_edf(path: Path, labels, signals, fs, units="uV", start_time="10.00.00"):
    """Write a minimal EDF file.

    Physical and digital ranges are both -32768..32767, so each sample is stored
    exactly as the integer value given (gain 1). Signals must be integer-valued.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    signals = [np.asarray(s) for s in signals]
    ns, n = len(labels), len(signals[0])
    fs = int(fs)
    assert n % fs == 0, "signal length must be a whole number of seconds"
    n_records = n // fs
    units = [units] * ns if isinstance(units, str) else list(units)

    def f(value, width):
        return str(value).ljust(width)[:width].encode("latin-1")

    header = (f("0", 8) + f("X", 80) + f("X", 80) + f("01.01.01", 8) + f(start_time, 8)
              + f(256 * (ns + 1), 8) + f("", 44) + f(n_records, 8) + f(1, 8) + f(ns, 4))
    header += b"".join(f(x, 16) for x in labels)
    header += b"".join(f("", 80) for _ in labels)
    header += b"".join(f(u, 8) for u in units)
    header += b"".join(f(-32768, 8) for _ in labels) + b"".join(f(32767, 8) for _ in labels)
    header += b"".join(f(-32768, 8) for _ in labels) + b"".join(f(32767, 8) for _ in labels)
    header += b"".join(f("", 80) for _ in labels)
    header += b"".join(f(fs, 8) for _ in labels)
    header += b"".join(f("", 32) for _ in labels)

    records = np.stack([s.astype("<i2").reshape(n_records, fs) for s in signals], axis=1)
    path.write_bytes(header + records.tobytes())
    return path
