# SeizeIT2 channel census

125 subjects, 2850 EEG files, 11626 hours.

### Channels present in the file

| channels | files | hours | share of hours |
|---|---:|---:|---:|
| BTEleft + CROSStop | 1434 | 5679 | 49% |
| BTEright + CROSStop | 906 | 3719 | 32% |
| BTEleft + BTEright | 510 | 2228 | 19% |

### Channels actually working (present and not flat)

| channels | files | hours | share of hours |
|---|---:|---:|---:|
| BTEleft + CROSStop | 1433 | 5679 | 49% |
| BTEright + CROSStop | 904 | 3717 | 32% |
| BTEleft + BTEright | 510 | 2228 | 19% |
| (none) | 1 | 1 | 0% |
| BTEright | 1 | 1 | 0% |
| CROSStop | 1 | 1 | 0% |

Files with a worn but flat channel: 3 of 2850 (CROSStop 2, BTEleft 1, BTEright 1).

### Patients by working-channel setup (all their files)

| setup | patients |
|---|---:|
| BTEleft + CROSStop | 64 |
| BTEright + CROSStop | 41 |
| BTEleft + BTEright | 16 |
| BTEleft + CROSStop / BTEright + CROSStop | 2 |
| (none) / BTEleft + CROSStop | 1 |
| BTEright / BTEright + CROSStop / CROSStop | 1 |

Flat = RMS under 1 µV in at least 80% of 12 one-minute samples spread over the file.
