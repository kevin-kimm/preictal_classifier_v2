"""Check the OpenBCI Cyton connection before Deliverable 3 (a preview of VT-22).

Streams for a set time with BrainFlow, then reports the measured sampling rate and packet
loss and saves the raw recording. Works without hardware using BrainFlow's simulated board,
so the setup can be tested now; with the real board, pass its serial port.

Usage, from the repo root with .venv active (pip install brainflow first):
    python scripts/cyton_check.py --board synthetic --seconds 60
    python scripts/cyton_check.py --board cyton --port /dev/cu.usbserial-XXXX --seconds 60
    python scripts/cyton_check.py --board cyton-daisy --port /dev/cu.usbserial-XXXX

Find the port with: ls /dev/cu.usbserial-*   (the Cyton's USB dongle must be plugged in and its
switch set to GPIO_6; the board's switch set to PC)

Output: data/live/check_<board>_<time>.csv (raw, not committed) and a summary on screen.
VT-22's pass criteria: sampling rate 250 ± 1 Hz and packet loss ≤ 1%.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
BOARDS = {"synthetic": "SYNTHETIC_BOARD", "cyton": "CYTON_BOARD", "cyton-daisy": "CYTON_DAISY_BOARD"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", choices=BOARDS, default="synthetic")
    ap.add_argument("--port", default="", help="serial port of the Cyton dongle, e.g. /dev/cu.usbserial-DM00XXXX")
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()
    try:
        from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
        from brainflow.data_filter import DataFilter
    except ImportError:
        sys.exit("BrainFlow isn't installed: pip install brainflow")
    if args.board != "synthetic" and not args.port:
        sys.exit("The real board needs --port (find it with: ls /dev/cu.usbserial-*)")

    board_id = getattr(BoardIds, BOARDS[args.board]).value
    params = BrainFlowInputParams()
    params.serial_port = args.port
    fs = BoardShim.get_sampling_rate(board_id)
    eeg = BoardShim.get_eeg_channels(board_id)
    pkg = BoardShim.get_package_num_channel(board_id)
    ts = BoardShim.get_timestamp_channel(board_id)

    board = BoardShim(board_id, params)
    print(f"Connecting to {args.board} ({len(eeg)} EEG channels, nominal {fs} Hz)...")
    board.prepare_session()
    board.start_stream(45000 * 10)
    t0 = time.time()
    try:
        while time.time() - t0 < args.seconds:
            time.sleep(1.0)
            print(f"\r  recording {time.time() - t0:5.0f} / {args.seconds:.0f} s", end="", flush=True)
    finally:
        data = board.get_board_data()
        board.stop_stream()
        board.release_session()
    print()

    n = data.shape[1]
    stamps = data[ts]
    duration = stamps[-1] - stamps[0] if n > 1 else float("nan")
    measured_fs = (n - 1) / duration if duration and duration > 0 else float("nan")
    counter = data[pkg].astype(int)
    step = 2 if args.board == "cyton-daisy" else 1
    jumps = np.diff(counter) % 256
    lost = int(np.sum(np.maximum(jumps // step - 1, 0)))
    loss = lost / max(n + lost, 1)
    eeg_uv = data[eeg]
    print(f"Samples: {n:,} over {duration:.1f} s -> measured rate {measured_fs:.2f} Hz (nominal {fs})")
    print(f"Packet loss: {lost} missing samples ({100 * loss:.2f}%)")
    print("Signal range per channel (µV, 1st-99th percentile): "
          + ", ".join(f"ch{i + 1} {np.percentile(x, 1):.0f}..{np.percentile(x, 99):.0f}" for i, x in enumerate(eeg_uv)))
    if args.board != "synthetic":
        ok_fs = abs(measured_fs - 250) <= 1 if args.board == "cyton" else abs(measured_fs - fs) <= 1
        print(f"VT-22 preview: rate {'OK' if ok_fs else 'CHECK'}; packet loss {'OK' if loss <= 0.01 else 'CHECK'}")

    out = REPO / "data" / "live"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"check_{args.board}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    DataFilter.write_file(data, str(path), "w")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
