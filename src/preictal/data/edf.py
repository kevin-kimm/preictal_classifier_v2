"""Minimal EDF reader.

Reads the header and only the channels that are asked for, scaled to physical
units. Kept separate from MNE so that duplicate channel labels (common in
CHB-MIT) and non-standard labels are handled explicitly by harmonize.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class EDFHeader:
    path: Path
    start_date: str            # dd.mm.yy as written in the file
    start_time: str            # hh.mm.ss as written in the file
    header_bytes: int
    n_records: int
    record_s: float
    labels: list[str]
    units: list[str]
    phys_min: np.ndarray
    phys_max: np.ndarray
    dig_min: np.ndarray
    dig_max: np.ndarray
    samples_per_record: np.ndarray

    @property
    def n_signals(self) -> int:
        return len(self.labels)

    @property
    def duration_s(self) -> float:
        return self.n_records * self.record_s

    def fs(self, i: int) -> float:
        return float(self.samples_per_record[i]) / self.record_s

    def start_seconds_of_day(self) -> int | None:
        """Header start time as seconds after midnight, or None if unreadable."""
        parts = self.start_time.replace(":", ".").split(".")
        try:
            h, m, s = (int(p) for p in parts[:3])
        except ValueError:
            return None
        return h * 3600 + m * 60 + s


def read_header(path: str | Path) -> EDFHeader:
    path = Path(path)
    size = path.stat().st_size
    with open(path, "rb") as f:
        fixed = f.read(256)
        if len(fixed) < 256:
            raise ValueError(f"{path.name}: shorter than the 256-byte EDF header")
        ns = int(fixed[252:256].decode("ascii").strip())
        sig = f.read(256 * ns)
    if len(sig) < 256 * ns:
        raise ValueError(f"{path.name}: signal header is truncated")

    def text(a, b):
        return fixed[a:b].decode("ascii", "replace").strip()

    def block(offset_per_signal, width):
        base = ns * offset_per_signal
        return [sig[base + i * width: base + (i + 1) * width].decode("latin-1").strip()
                for i in range(ns)]

    header_bytes = int(text(184, 192))
    n_records = int(text(236, 244))
    record_s = float(text(244, 252))
    spr = np.array([int(x) for x in block(216, 8)], dtype=np.int64)
    if n_records < 0:  # unknown in header: infer from file size
        n_records = (size - header_bytes) // int(2 * spr.sum())

    return EDFHeader(
        path=path,
        start_date=text(168, 176),
        start_time=text(176, 184),
        header_bytes=header_bytes,
        n_records=n_records,
        record_s=record_s,
        labels=block(0, 16),
        units=block(96, 8),
        phys_min=np.array([float(x) for x in block(104, 8)]),
        phys_max=np.array([float(x) for x in block(112, 8)]),
        dig_min=np.array([float(x) for x in block(120, 8)]),
        dig_max=np.array([float(x) for x in block(128, 8)]),
        samples_per_record=spr,
    )


def read_signals(hdr: EDFHeader, indices: list[int], first_record: int = 0,
                 n_records: int | None = None) -> list[np.ndarray]:
    """Read the given channels, scaled to the physical units in the header (float64).

    first_record and n_records select a stretch of data records (each record_s
    seconds long) so long recordings can be read in pieces.
    """
    spr = hdr.samples_per_record
    record_len = int(spr.sum())
    offsets = np.concatenate([[0], np.cumsum(spr)])
    first_record = max(0, int(first_record))
    last = hdr.n_records if n_records is None else min(hdr.n_records, first_record + int(n_records))
    data = np.memmap(hdr.path, dtype="<i2", mode="r", offset=hdr.header_bytes,
                     shape=(hdr.n_records, record_len))
    out = []
    for i in indices:
        digital = np.asarray(data[first_record:last, offsets[i]:offsets[i + 1]], dtype=np.float64).reshape(-1)
        span = hdr.dig_max[i] - hdr.dig_min[i]
        gain = (hdr.phys_max[i] - hdr.phys_min[i]) / span if span else 1.0
        out.append((digital - hdr.dig_min[i]) * gain + hdr.phys_min[i])
    del data
    return out
