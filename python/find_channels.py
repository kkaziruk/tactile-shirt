"""
Channel finder: works out which mux channels each sensor strip is on.

1. Flash firmware/channel_finder/channel_finder.ino to the ESP32.
2. python3 find_channels.py /dev/cu.usbserial-0001
3. Follow the prompts: press and hold each corner until it says "got it",
   then let go.
4. It prints the exact lines to paste into tactile_shirt.ino.
"""

import sys
import time

import numpy as np
import serial

if len(sys.argv) < 2:
    sys.exit("usage: python3 find_channels.py <port>")

ser = serial.Serial(sys.argv[1], 250000, timeout=0.5)
time.sleep(2)
ser.reset_input_buffer()

PRESS_V = 0.08     # minimum drop that counts as a press
STABLE = 4         # frames the same pair must win in a row


def frame():
    while True:
        parts = ser.readline().decode(errors="ignore").strip().split(",")
        if len(parts) == 257 and parts[0] == "M":
            try:
                return np.array(parts[1:], dtype=float).reshape(16, 16) / 1000
            except ValueError:
                pass


print("Calibrating - hands OFF both sensors...")
base = np.mean([frame() for _ in range(10)], axis=0)
print("Done.\n")


def wait_press():
    last, count = None, 0
    while True:
        drop = base - frame()
        r, c = np.unravel_index(np.argmax(drop), drop.shape)
        if drop[r, c] < PRESS_V:
            last, count = None, 0
            continue
        count = count + 1 if (r, c) == last else 1
        last = (r, c)
        if count >= STABLE:
            return int(r), int(c), float(drop[r, c])


def wait_release():
    while (base - frame()).max() > PRESS_V / 2:
        pass


CORNERS = [("TOP-LEFT", "R1 C1"), ("TOP-RIGHT", "R1 C7"),
           ("BOTTOM-LEFT", "R6 C1"), ("BOTTOM-RIGHT", "R6 C7")]
results = {}
for sensor in ("CHEST", "BACK"):
    for name, label in CORNERS:
        input(f">> {sensor} {name} corner ({label}) - press Enter, then press and hold it...")
        r, c, v = wait_press()
        print(f"   got it: row-mux ch {r}, col-mux ch {c}  ({v:.2f} V). Let go.")
        results[(sensor, name)] = (r, c)
        wait_release()
    print()


def strip(a, b, n):
    """Channels from a to b inclusive, expected to be n strips long."""
    step = 1 if b >= a else -1
    chans = list(range(a, b + step, step))
    return chans if len(chans) == n else None


print("=" * 60)
print("RESULTS (send this whole block to Claude if anything looks odd)")
for k, v in results.items():
    print(f"  {k[0]:5} {k[1]:12} -> row-mux {v[0]:2}, col-mux {v[1]:2}")
print()

lines, ok = [], True
for idx, sensor in enumerate(("CHEST", "BACK")):
    tl, tr = results[(sensor, "TOP-LEFT")], results[(sensor, "TOP-RIGHT")]
    bl = results[(sensor, "BOTTOM-LEFT")]
    # Moving along a physical row (TL -> TR) changes exactly one mux:
    transposed = tl[0] != tr[0]   # row-mux changes -> columns are on the row mux
    m_col = 0 if transposed else 1
    m_row = 1 - m_col
    cols = strip(tl[m_col], tr[m_col], 7)
    rows = strip(tl[m_row], bl[m_row], 6)
    if cols is None or rows is None:
        ok = False
        print(f"  {sensor}: channels are not a simple run - send the RESULTS block to Claude.")
        continue
    lines.append((idx, transposed, rows, cols))

if ok:
    print("Paste these into tactile_shirt.ino (replacing the existing lines):\n")
    t = ", ".join("1" if x[1] else "0" for x in lines)
    r = ", ".join("{" + ", ".join(map(str, x[2])) + "}" for x in lines)
    c = ", ".join("{" + ", ".join(map(str, x[3])) + "}" for x in lines)
    print(f"const uint8_t TRANSPOSED[2] = {{{t}}};")
    print(f"const uint8_t ROW_STRIP[2][ROWS] = {{{r}}};")
    print(f"const uint8_t COL_STRIP[2][COLS] = {{{c}}};")
