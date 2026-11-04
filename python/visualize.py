"""
Tactile Exercise Shirt - live dashboard + data logging.

Shows, for the chest and back sensors:
  - smooth pressure heatmap (auto-brightness, so light presses still show)
  - center of pressure (cyan ring)
  - left / right balance bar
  - total pressure over the last 10 seconds (one bump per rep)

Keys (click the window first):
  c  recalibrate (take hands off the sensors first)
  v  show / hide numbers in each cell
  s  switch smooth <-> blocky cells
  f  freeze / unfreeze the display

Usage:
  pip3 install pyserial numpy matplotlib
  python3 visualize.py /dev/cu.usbserial-0001
  python3 visualize.py COM3 --log reps.csv --label wide_grip
  python3 visualize.py /dev/cu.usbserial-0001 --flip-back
"""

import argparse
import csv
import queue
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
import numpy as np
import serial
from matplotlib.animation import FuncAnimation
from matplotlib.gridspec import GridSpec

ROWS, COLS = 6, 7
N = ROWS * COLS
HISTORY_S = 10

ap = argparse.ArgumentParser()
ap.add_argument("port")
ap.add_argument("--baud", type=int, default=250000)
ap.add_argument("--calib", type=int, default=30, help="frames used for the baseline")
ap.add_argument("--alpha", type=float, default=0.5, help="smoothing 0-1 (1 = off)")
ap.add_argument("--threshold", type=float, default=0.03, help="ignore drops below this (V)")
ap.add_argument("--vmin-scale", type=float, default=0.15,
                help="lowest color ceiling (V); auto-brightness never goes below this")
ap.add_argument("--vmax", type=float, default=None, help="fixed color ceiling (V), disables auto")
ap.add_argument("--flip-chest", action="store_true", help="mirror chest left/right")
ap.add_argument("--flip-back", action="store_true", help="mirror back left/right")
ap.add_argument("--log", help="CSV file to append raw frames to")
ap.add_argument("--label", default="", help="label saved with each logged frame")
args = ap.parse_args()

ser = serial.Serial(args.port, args.baud, timeout=0.1)
time.sleep(2)  # the ESP32 resets when the port opens
ser.reset_input_buffer()


def parse(raw_line):
    parts = raw_line.decode("utf-8", errors="ignore").strip().split(",")
    if len(parts) != 2 + 2 * N or parts[0] != "F":
        return None
    try:
        t = int(parts[1])
        v = np.array(parts[2:], dtype=float)
    except ValueError:
        return None
    return t, v[:N].reshape(ROWS, COLS), v[N:].reshape(ROWS, COLS)


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

# ---------- Serial thread ----------
data_q = queue.Queue()


def reader():
    while True:
        try:
            f = parse(ser.readline())
        except (serial.SerialException, OSError):
            data_q.put(None)
            break
        if f:
            if writer:
                t, c, b = f
                writer.writerow([t, args.label]
                                + [f"{x:.3f}" for x in c.ravel()]
                                + [f"{x:.3f}" for x in b.ravel()])
            data_q.put(f)


threading.Thread(target=reader, daemon=True).start()

# ---------- State ----------
state = {
    "base": None,          # (chest, back) baselines
    "calib": [],           # frames collected while calibrating
    "smooth": [np.zeros((ROWS, COLS)), np.zeros((ROWS, COLS))],
    "scale": args.vmin_scale,
    "values": False,
    "blocky": False,
    "frozen": False,
    "disconnected": False,
}
hist_t = deque()
hist = [deque(), deque()]
arrivals = deque()
flip = [args.flip_chest, args.flip_back]


def start_calibration():
    state["base"] = None
    state["calib"] = []
    state["smooth"] = [np.zeros((ROWS, COLS)), np.zeros((ROWS, COLS))]


def pressure(raw, base):
    """Pressure lowers the voltage, so the signal is baseline minus reading."""
    p = base - raw
    p[p < args.threshold] = 0
    return p


def center_of_pressure(p):
    total = p.sum()
    if total <= 0:
        return None
    rr, cc = np.mgrid[0:ROWS, 0:COLS]
    return (cc * p).sum() / total, (rr * p).sum() / total


def left_share(p):
    left, right = p[:, : COLS // 2].sum(), p[:, COLS // 2 + 1:].sum()
    return None if left + right == 0 else left / (left + right)


# ---------- Figure ----------
plt.rcParams.update({"font.size": 11, "axes.titleweight": "bold"})
BG, FG, DIM = "#0f1115", "#e8e8ea", "#8a8f98"
COLORS = ["#4cc9f0", "#f72585"]  # chest, back

fig = plt.figure(figsize=(13, 8.5), facecolor=BG)
fig.canvas.manager.set_window_title("Tactile Shirt - live")
gs = GridSpec(3, 2, figure=fig, height_ratios=[5, 0.35, 2.2],
              hspace=0.45, wspace=0.12, left=0.05, right=0.97, top=0.9, bottom=0.07)
title = fig.suptitle("", color=FG, fontsize=15, fontweight="bold")

views = []
for i, name in enumerate(["CHEST", "BACK"]):
    ax = fig.add_subplot(gs[0, i])
    ax.set_facecolor(BG)
    im = ax.imshow(np.zeros((ROWS, COLS)), cmap="magma", vmin=0, vmax=state["scale"],
                   interpolation="bicubic", aspect="equal")
    ax.set_title(name, color=COLORS[i], fontsize=14, pad=8)
    ax.set_xticks(range(COLS), [f"C{c + 1}" for c in range(COLS)], color=DIM, fontsize=9)
    ax.set_yticks(range(ROWS), [f"R{r + 1}" for r in range(ROWS)], color=DIM, fontsize=9)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_color("#2a2e36")
    ax.axvline((COLS - 1) / 2, color="white", ls=(0, (3, 4)), lw=0.8, alpha=0.4)
    (ring,) = ax.plot([], [], "o", ms=22, mfc="none", mec="#00f5d4", mew=3)
    peak = ax.text(0.98, 0.02, "", transform=ax.transAxes, ha="right", va="bottom",
                   color=FG, fontsize=10,
                   bbox=dict(boxstyle="round,pad=0.3", fc="#000000aa", ec="none"))
    cells = [[ax.text(c, r, "", ha="center", va="center", fontsize=8, color="white")
              for c in range(COLS)] for r in range(ROWS)]

    # Left/right balance bar
    bx = fig.add_subplot(gs[1, i])
    bx.set_facecolor("#1b1e24")
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.set_xticks([])
    bx.set_yticks([])
    for s in bx.spines.values():
        s.set_visible(False)
    lbar = bx.barh(0.5, 0.5, height=1, color=COLORS[i], alpha=0.85, left=0)[0]
    rbar = bx.barh(0.5, 0.5, height=1, color="#3a3f4b", left=0.5)[0]
    bx.axvline(0.5, color="white", lw=1.5)
    btxt = bx.text(0.5, 0.5, "", ha="center", va="center", color=FG, fontsize=11,
                   fontweight="bold")
    views.append(dict(ax=ax, im=im, ring=ring, peak=peak, cells=cells,
                      lbar=lbar, rbar=rbar, btxt=btxt))

# Total pressure over time
tx = fig.add_subplot(gs[2, :])
tx.set_facecolor("#15181e")
for s in tx.spines.values():
    s.set_color("#2a2e36")
tx.tick_params(colors=DIM, labelsize=9)
tx.set_xlim(-HISTORY_S, 0)
tx.set_ylim(0, 1)
tx.set_xlabel("seconds", color=DIM, fontsize=9)
tx.set_ylabel("total pressure (V)", color=DIM, fontsize=9)
tx.grid(color="#2a2e36", lw=0.6)
lines = [tx.plot([], [], color=COLORS[i], lw=2.2, label=n)[0]
         for i, n in enumerate(["chest", "back"])]
tx.legend(loc="upper left", facecolor="#15181e", edgecolor="#2a2e36", labelcolor=FG,
          fontsize=9)

status = fig.text(0.05, 0.015, "", color=DIM, fontsize=9)
fig.text(0.97, 0.015, "c recalibrate · v values · s smooth/blocky · f freeze",
         color=DIM, fontsize=9, ha="right")


def on_key(event):
    if event.key == "c":
        start_calibration()
    elif event.key == "v":
        state["values"] = not state["values"]
    elif event.key == "s":
        state["blocky"] = not state["blocky"]
        for v in views:
            v["im"].set_interpolation("nearest" if state["blocky"] else "bicubic")
    elif event.key == "f":
        state["frozen"] = not state["frozen"]


fig.canvas.mpl_connect("key_press_event", on_key)


def update(_):
    now = time.time()
    got = False
    while not data_q.empty():
        f = data_q.get()
        if f is None:
            state["disconnected"] = True
            break
        _, chest, back = f
        arrivals.append(now)
        if state["base"] is None:
            state["calib"].append((chest, back))
            if len(state["calib"]) >= args.calib:
                state["base"] = (np.mean([x[0] for x in state["calib"]], axis=0),
                                 np.mean([x[1] for x in state["calib"]], axis=0))
            continue
        got = True
        for i, raw in enumerate((chest, back)):
            p = pressure(raw, state["base"][i])
            state["smooth"][i] = args.alpha * p + (1 - args.alpha) * state["smooth"][i]

    while arrivals and arrivals[0] < now - 1:
        arrivals.popleft()

    if state["disconnected"]:
        title.set_text("DISCONNECTED - replug the ESP32 and restart")
        title.set_color("#ff5d5d")
        return
    if state["base"] is None:
        title.set_text(f"Calibrating... hands off  ({len(state['calib'])}/{args.calib})")
        title.set_color("#ffd166")
        return
    title.set_text("LIVE" if not state["frozen"] else "FROZEN (press f)")
    title.set_color("#06d6a0" if not state["frozen"] else "#ffd166")
    status.set_text(f"{len(arrivals)} frames/s")
    if not got or state["frozen"]:
        return

    grids = [np.fliplr(g) if flip[i] else g for i, g in enumerate(state["smooth"])]

    # Auto-brightness: color ceiling follows the strongest recent press.
    if args.vmax:
        scale = args.vmax
    else:
        peak_now = max(g.max() for g in grids)
        target = max(args.vmin_scale, peak_now * 1.15)
        scale = state["scale"] + (0.3 if target > state["scale"] else 0.03) * (target - state["scale"])
        state["scale"] = scale

    hist_t.append(now)
    for i, g in enumerate(grids):
        hist[i].append(g.sum())
    while hist_t and hist_t[0] < now - HISTORY_S:
        hist_t.popleft()
        for h in hist:
            h.popleft()

    for i, (v, g) in enumerate(zip(views, grids)):
        v["im"].set_data(g)
        v["im"].set_clim(0, scale)
        cop = center_of_pressure(g)
        v["ring"].set_data(([cop[0]], [cop[1]]) if cop else ([], []))
        v["peak"].set_text(f"peak {g.max():.2f} V" if g.max() > 0 else "no contact")
        for r in range(ROWS):
            for c in range(COLS):
                v["cells"][r][c].set_text(
                    f"{g[r, c]:.2f}" if state["values"] and g[r, c] > 0 else "")
        share = left_share(g)
        if share is None:
            v["lbar"].set_width(0)
            v["rbar"].set_x(0)
            v["rbar"].set_width(1)
            v["btxt"].set_text("no contact")
        else:
            v["lbar"].set_width(share)
            v["rbar"].set_x(share)
            v["rbar"].set_width(1 - share)
            v["btxt"].set_text(f"L {share * 100:.0f}%   |   R {(1 - share) * 100:.0f}%")

    ts = np.array(hist_t) - now
    top = 0.2
    for i, line in enumerate(lines):
        y = np.array(hist[i])
        line.set_data(ts, y)
        if len(y):
            top = max(top, y.max() * 1.2)
    tx.set_ylim(0, top)


ani = FuncAnimation(fig, update, interval=40, cache_frame_data=False)
plt.show()

ser.close()
if log_file:
    log_file.close()
