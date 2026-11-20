These partition tables are used for the full flash images (`.bin`), not for the
application images (`.ota`).

The generic builder in `lvgl_micropython/builder/esp32.py` pads the partition
preamble, which puts `ota_0` at `0x20000`. The tables here keep the 64 KiB
preamble compact (`ota_0` at `0x10000`) and reserve the same filesystem offsets
as the Fri3d Camp badge firmware, so the preloaded filesystem image has the same
layout everywhere and can be produced once.

| File | Target |
|------|--------|
| `esp32s3_16mb_badge.csv` | ESP32-S3 with 16 MB flash; byte-identical to `badge_firmware_MicroPythonOS/boards/shared/partitions.16mb.csv` |
| `esp32_16mb.csv` | ESP32 (non-S3) with 16 MB flash; 0x390000 app slots because the esp32 build is larger |
| `esp32s3_8mb_unphone.csv` | unPhone (8 MB flash, no OTA) |
| `esp32p4_32mb.csv` | ESP32-P4 with 32 MB flash (4 MiB OTA slots) |

`scripts/build_mpos.sh` reads the table from here when it builds the final
image. The app and `.ota` images do not depend on the partition offsets, so
changing the table only affects a full re-flash; in-place OTA updates keep
working on devices that still have an older table.
