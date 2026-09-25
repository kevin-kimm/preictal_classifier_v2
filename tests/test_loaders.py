"""Annotation parsing tests (support VT-05) and subject IDs (support VT-08)."""

import numpy as np
import pytest

from conftest import write_edf
from preictal.data.loaders import (
    chbmit_annotations, discover, match_siena_file, parse_clock, seconds_after,
    siena_blocks, tuh_seizures,
)


@pytest.mark.parametrize("text, expected", [
    ("19.58.36", 19 * 3600 + 58 * 60 + 36),
    ("21:51:02", 21 * 3600 + 51 * 60 + 2),
    ("16:13.23", 16 * 3600 + 13 * 60 + 23),        # mixed separators (PN12)
    ("  18.20.24", 18 * 3600 + 20 * 60 + 24),
    ("15.43.53 (CLINICAL ONSET); 15.43.59 (ELECTRIC ONSET)", 15 * 3600 + 43 * 60 + 59),
    ("no time here", None),
])
def test_parse_clock(text, expected):
    assert parse_clock(text) == expected


def test_seconds_after_midnight_rollover():
    t0 = 19 * 3600 + 39 * 60 + 33      # recording starts 19:39:33
    t = 2 * 3600 + 38 * 60 + 37        # seizure at 02:38:37 the next morning
    assert seconds_after(t, t0) == (24 * 3600 - t0) + t


def test_siena_blocks(tmp_path):
    f = tmp_path / "Seizures-list-PN03.txt"
    f.write_text("Seizures list\n\nSeizure n1\nFile name: PN03-1.edf\n"
                 "Registration start time: 09.00.00\nSeizure start time:09.29.10\n"
                 "Seizure end time: 09.30.00\n\nSeizure n 2\nFile name: PN03-2.edf\n"
                 "Start time: 07:13:05\nEnd time: 07:14:00\n"
                 "Electrodes involved at start of seizure: F3-C3\n")
    blocks = siena_blocks(f)
    assert [b["file"] for b in blocks] == ["PN03-1.edf", "PN03-2.edf"]
    assert blocks[0]["start"] == 9 * 3600 + 29 * 60 + 10
    assert blocks[1]["end"] == 7 * 3600 + 14 * 60


def test_siena_blocks_file_name_before_heading(tmp_path):
    f = tmp_path / "Seizures-list-PN11.txt"
    f.write_text("Seizures list of patient PN11\nFile name: PN11-1.edf\n\nSeizure n 1:\n"
                 "Seizure start time: 13.37.19\nSeizure end time: 13.38.00\n\n"
                 "File name: PN11-2.edf\nSeizure n 2:\nStart time: 14.00.00\nEnd time: 14.01.00\n")
    blocks = siena_blocks(f)
    assert [b["file"] for b in blocks] == ["PN11-1.edf", "PN11-2.edf"]


def test_siena_blocks_without_file_name(tmp_path):
    f = tmp_path / "Seizures-list-PN99.txt"
    f.write_text("Seizure n 1:\nSeizure start time: 13.37.19\nSeizure end time: 13.38.00\n")
    assert siena_blocks(f)[0].get("file") is None


def test_match_siena_file(tmp_path):
    names = ["PN06-1.edf", "PN06-2.edf"]
    by_name = {n.lower(): tmp_path / n for n in names}
    assert match_siena_file("PN06-1.edf", by_name, [])[1] == ""
    assert match_siena_file("PNO6-2.edf", by_name, [])[1] == "letter O typed for zero"
    only = [tmp_path / "PN01-1.edf"]
    assert match_siena_file("PN01.edf", {}, only) == (only[0], "only EDF for this patient")
    assert match_siena_file("PN99-9.edf", by_name, [])[0] is None


def test_chbmit_annotations(tmp_path):
    (tmp_path / "chb05").mkdir()
    (tmp_path / "chb05" / "chb05-summary.txt").write_text(
        "File Name: chb05_06.edf\nNumber of Seizures in File: 1\n"
        "Seizure Start Time: 417 seconds\nSeizure End Time: 532 seconds\n\n"
        "File Name: chb05_07.edf\nNumber of Seizures in File: 2\n"
        "Seizure 1 Start Time: 10 seconds\nSeizure 1 End Time: 20 seconds\n"
        "Seizure 2 Start Time: 100 seconds\nSeizure 2 End Time: 130 seconds\n\n"
        "File Name: chb05_08.edf\nNumber of Seizures in File: 0\n")
    ann, notes = chbmit_annotations(tmp_path)
    assert ann["chb05_06.edf"] == [(417.0, 532.0)]
    assert ann["chb05_07.edf"] == [(10.0, 20.0), (100.0, 130.0)]
    assert ann["chb05_08.edf"] == []
    assert notes == []


def test_tuh_seizures(tmp_path):
    f = tmp_path / "x.csv_bi"
    f.write_text("# version = csv_v1.0.0\n#\nchannel,start_time,stop_time,label,confidence\n"
                 "TERM,0.0000,36.8868,bckg,1.0000\nTERM,36.8868,183.3055,seiz,1.0000\n"
                 "TERM,183.3055,301.0000,bckg,1.0000\n")
    assert tuh_seizures(f) == [(36.8868, 183.3055)]


def test_subject_ids_and_siena_times(tmp_path):
    root = tmp_path / "raw"
    z = np.zeros(256 * 2)
    write_edf(root / "chbmit_v1.0.0/chb01/chb01_01.edf", ["FP1-F7"], [z], 256)
    write_edf(root / "chbmit_v1.0.0/chb21/chb21_01.edf", ["FP1-F7"], [z], 256)
    write_edf(root / "tusz_v2.0.6/edf/train/aaaaaaac/s001_2002/01_tcp_ar/aaaaaaac_s001_t000.edf",
              ["EEG FP1-REF"], [z], 256)
    write_edf(root / "tuar_v3.0.1/edf/01_tcp_ar/aaaaaaac_s003_t000.edf", ["EEG FP1-REF"], [z], 256)
    write_edf(root / "siena_v1.0.0/PN06/PN06-1.edf", ["EEG Fp1"], [z], 256, start_time="23.50.00")
    (root / "siena_v1.0.0/PN06/Seizures-list-PN06.txt").write_text(
        "Seizure n 1:\nFile name: PNO6-1.edf\nRegistration start time: 23.49.00\n"
        "Seizure start time: 00.05.00\nSeizure end time: 00.06.30\n")
    notes = []
    recs = {r.rel_path.split("/")[-1]: r for r in discover(root, notes=notes)}
    assert recs["chb21_01.edf"].subject == recs["chb01_01.edf"].subject == "chbmit:chb01"
    assert recs["aaaaaaac_s001_t000.edf"].subject == recs["aaaaaaac_s003_t000.edf"].subject == "tuh:aaaaaaac"
    # Siena: 23:50:00 start, seizure at 00:05:00 -> 15 min in; typo in file name corrected and logged
    assert recs["PN06-1.edf"].seizures == [(900.0, 990.0)]
    assert any("letter O typed for zero" in n for n in notes)
    assert any("the EDF header time is used" in n for n in notes)  # 23:49 in list vs 23:50 in header
