# Tactile Exercise Shirt

Two 6×7 Velostat pressure grids (chest + back) read by an ESP32 through four CD74HC4067 multiplexers, with a live Python heatmap. Built for EE546 Emerging Interactive Technologies, Lab 6.

Based on the course scanning and visualization code: https://github.com/WellingtonMiao/EE546-EMERGING-INTERACTIVE-TECHNOLOGIES, extended from one 4×4 sensor to two 6×7 sensors.

## Wiring

Each sensor uses the course schematic: one **sense mux** (MUX1) and one **ground mux** (MUX2).

| | Chest | Back |
|---|---|---|
| Sense mux C0–C6 | 7 vertical strips | 7 vertical strips |
| Sense mux S0–S3 | GPIO 33, 25, 26, 27 (shared) | same |
| Sense mux SIG | GPIO 36 (VP) + 660 Ω to 3V3 | GPIO 39 (VN) + its own 660 Ω to 3V3 |
| Ground mux C0–C5 | 6 horizontal strips | 6 horizontal strips |
| Ground mux S0–S3 | GPIO 21, 22, 23, 14 (shared) | same |
| Ground mux SIG | GND | GND |
| EN / VCC | GND / 3V3 | GND / 3V3 |

The selected horizontal strip is grounded and the selected vertical strip is pulled up to 3.3 V, so the Velostat forms a voltage divider: unpressed reads near 3.3 V, and pressing lowers the voltage. If a strip is on a different mux channel, edit `ROW_CH` / `COL_CH` at the top of the firmware.

## Run it

1. Open `firmware/tactile_shirt/tactile_shirt.ino` in Arduino IDE → Board: **ESP32 Dev Module** → Upload (hold BOOT if it stalls).
2. Close the Serial Monitor.
3. `pip install -r python/requirements.txt`
4. `python python/visualize.py COM3` (Mac: `/dev/cu.usbserial-XXXX`)
5. Keep both sensors unloaded for ~2 s while it calibrates.

Options: `--flip-chest` / `--flip-back` to mirror a heatmap, `--log reps.csv --label wide_grip` to save labeled frames, `--no-values` to hide cell numbers.

## Data format

One line per frame at 250000 baud:

```
F,<ms since boot>,<42 chest voltages row by row>,<42 back voltages row by row>
```

## Troubleshooting

- **Stuck on "Calibrating":** wrong port/baud, or Serial Monitor still open.
- **A whole row or column is dead:** bad splice on that strip, or a channel mismatch in `ROW_CH` / `COL_CH`.
- **A whole sensor reads flat:** that mux's EN isn't on GND, or its 660 Ω resistor is missing.
