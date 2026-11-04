"""
Tactile Exercise Shirt - live heatmaps + data logging (Lab 6).

Reads frames from the ESP32, measures a no-load baseline, and shows live
heatmaps of the chest and back grids with:
  - pressure at each point (voltage DROP from baseline, in volts)
  - center of pressure (cyan dot)
  - left/right balance, as shown on screen

Usage:
  pip install pyserial numpy matplotlib
  python visualize.py COM3                      # Windows
  python visualize.py /dev/cu.usbserial-0001    # Mac
  python visualize.py COM3 --log reps.csv --label wide_grip_good
  python visualize.py COM3 --flip-back          # mirror the back heatmap

Keep the shirt unloaded for the first few seconds while it calibrates.
"""

import argparse
import csv
import queue
import threading
import time

import matplotlib.pyplot as plt
import numpy as np
import serial
from matplotlib.animation import FuncAnimation

ROWS, COLS = 6, 7
N = ROWS * COLS

ap = argparse.ArgumentParser()
ap.add_argument("port")
ap.add_argument("--baud", type=int, default=250000)
ap.add_argument("--calib", type=int, default=50, help="frames used for the baseline")
ap.add_argument("--alpha", type=float, default=0.4, help="smoothing 0-1 (1 = off)")
ap.add_argument("--vmax", type=float, default=1.5, help="color ceiling, volts of drop")
ap.add_argument("--threshold", type=float, default=0.05, help="ignore drops below this (V)")
ap.add_argument("--flip-chest", action="store_true", help="mirror chest left/right")
ap.add_argument("--flip-back", action="store_true", help="mirror back left/right")
ap.add_argument("--no-values", action="store_true", help="hide numbers in cells")
ap.add_argument("--log", help="CSV file to append raw frames to")
ap.add_argument("--label", default="", help="label saved with each logged frame")
args = ap.parse_args()

ser = serial.Serial(args.port, args.baud, timeout=0.1)
time.sleep(2)  # the ESP32 resets when the port opens
ser.reset_input_buffer()


def parse(raw_line):
    parts = raw_line.decode("utf-8", errors="ignore").strip().split(",")
    if len(parts) != 2 + 2 * N or parts[0] != "F":
        return None  # boot message or a partial line
    try:
        t = int(parts[1])
        v = np.array(parts[2:], dtype=float)
    except ValueError:
        return None
    return t, v[:N].reshape(ROWS, COLS), v[N:].reshape(ROWS, COLS)


# ---------- Baseline ----------
print(f"Calibrating on {args.calib} frames - keep both sensors unloaded...")
frames = []
while len(frames) < args.calib:
    f = parse(ser.readline())
    if f:
        frames.append(f)
base_chest = np.mean([f[1] for f in frames], axis=0)
base_back = np.mean([f[2] for f in frames], axis=0)
print("Baseline (V), chest:\n", np.round(base_chest, 2))
print("Baseline (V), back:\n", np.round(base_back, 2))
print("Calibrated. Close the window to stop.")

# ---------- Logging ----------
writer = log_file = None
if args.log:
    log_file = open(args.log, "a", newline="")
    writer = csv.writer(log_file)
    if log_file.tell() == 0:
        writer.writerow(
            ["time_ms", "label"]
            + [f"chest_r{r}c{c}" for r in range(ROWS) for c in range(COLS)]
            + [f"back_r{r}c{c}" for r in range(ROWS) for c in range(COLS)]
        )

# ---------- Serial thread (keeps the window responsive) ----------
data_q = queue.Queue()


def reader():
    while True:
        try:
            f = parse(ser.readline())
        except serial.SerialException:
            break
        if f:
            if writer:
                t, c, b = f
                writer.writerow([t, args.label]
                                + [f"{x:.3f}" for x in c.ravel()]
                                + [f"{x:.3f}" for x in b.ravel()])
            data_q.put(f)


threading.Thread(target=reader, daemon=True).start()


# ---------- Processing ----------
def pressure(raw, base):
    """Pressure lowers the voltage, so the signal is baseline minus reading."""
    p = base - raw
    p[p < args.threshold] = 0
    return p


def center_of_pressure(p):
    total = p.sum()
    if total == 0:
        return None
    rr, cc = np.mgrid[0:ROWS, 0:COLS]
    return (cc * p).sum() / total, (rr * p).sum() / total


def balance(p):
    left, right = p[:, : COLS // 2].sum(), p[:, COLS // 2 + 1:].sum()  # middle column excluded
    if left + right == 0:
        return "no contact"
    return f"L {100 * left / (left + right):.0f}%  |  R {100 * right / (left + right):.0f}%"


# ---------- Plot ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
views = []
for ax, title in zip(axes, ["Chest", "Back"]):
    im = ax.imshow(np.zeros((ROWS, COLS)), cmap="inferno", vmin=0, vmax=args.vmax)
    ax.set_title(title)
    ax.set_xticks(range(COLS), [f"C{i + 1}" for i in range(COLS)])
    ax.set_yticks(range(ROWS), [f"R{i + 1}" for i in range(ROWS)])
    ax.axvline((COLS - 1) / 2, color="white", ls="--", lw=0.8)  # midline
    (dot,) = ax.plot([], [], "o", ms=16, mfc="none", mec="cyan", mew=2.5)
    bal = ax.text(0.5, -0.13, "", transform=ax.transAxes, ha="center", fontsize=11)
    cells = [] if args.no_values else [
        [ax.text(c, r, "", ha="center", va="center", fontsize=8, color="white")
         for c in range(COLS)] for r in range(ROWS)]
    fig.colorbar(im, ax=ax, fraction=0.04, label="Pressure (V drop)")
    views.append((im, dot, bal, cells))
fps_text = fig.text(0.01, 0.01, "")

smooth = [np.zeros((ROWS, COLS)), np.zeros((ROWS, COLS))]
flip = [args.flip_chest, args.flip_back]
arrivals = []


def update(_):
    got = False
    while not data_q.empty():
        _, chest, back = data_q.get()
        got = True
        arrivals.append(time.time())
        for i, (raw, base) in enumerate([(chest, base_chest), (back, base_back)]):
            smooth[i] = args.alpha * pressure(raw, base) + (1 - args.alpha) * smooth[i]
    if not got:
        return

    for i, (im, dot, bal, cells) in enumerate(views):
        grid = np.fliplr(smooth[i]) if flip[i] else smooth[i]
        im.set_data(grid)
        cop = center_of_pressure(grid)
        dot.set_data([cop[0]], [cop[1]]) if cop else dot.set_data([], [])
        bal.set_text(balance(grid))
        for r, row in enumerate(cells):
            for c, txt in enumerate(row):
                txt.set_text(f"{grid[r, c]:.2f}" if grid[r, c] > 0 else "")

    now = time.time()
    arrivals[:] = [t for t in arrivals if t > now - 1]
    fps_text.set_text(f"{len(arrivals)} frames/s")


ani = FuncAnimation(fig, update, interval=40, cache_frame_data=False)
plt.tight_layout()
plt.show()

ser.close()
if log_file:
    log_file.close()
