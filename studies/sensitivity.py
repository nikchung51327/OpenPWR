#!/usr/bin/env python3
"""Sensitivity of the axial behaviour to the two free parameters.

`F_couple` and `rho_xe_full` come from neither source paper (see the FREE
PARAMETERS block at the top of `Params`).  This script sweeps each one with the
other at its default and measures, per value:

  (a) trim invariance  -- a guard: the symmetric 100 % trim must not move
  (b) linear mode      -- rightmost eigenvalue of the linearisation there
  (c) open-loop tilt   -- nonlinear, 12 h, no controllers, after a rod pulse
  (d) closed-loop cost -- 24 h load-follow with AxialOffsetBand(band=0.03)

and bisects the two qualitative transitions in `rho_xe_full`.  It measures; it
does not assert anything except (a).  Findings: docs/SENSITIVITY.md.

    python studies/sensitivity.py              # everything, figures + CSV
    python studies/sensitivity.py --quick      # (a) and (b) only, no files
    python studies/sensitivity.py --F-couple 12 --rho-xe -0.034
                                               # one point, printed, no files

Writes studies/sensitivity_results.csv and studies/figures/sensitivity_*.png.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np

# Running a script puts studies/ on sys.path, not the repo root.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from pwr_plant import (ClosedLoop, Manual, Params, Plant, Result,   # noqa: E402
                       linearize, ramp, trim, turbine_leading)

F_DEFAULT, XE_DEFAULT = Params().F_couple, Params().rho_xe_full
F_GRID = [1.0, 2.5, 5.6, 8.0, 12.0, 18.0, 25.0]
XE_GRID = [-0.010, -0.014, -0.018, -0.022, -0.028, -0.034, -0.040, -0.045]

# (d) was specified as a 4-point subset "because it is the expensive one".  It
# costs about 5 s a run on this model, so it runs on every grid point.
F_CLOSED = F_GRID
XE_CLOSED = XE_GRID

BAND = 0.03                    # AxialOffsetBand half-width
T_OPEN = 12 * 3600.0           # (c)
T_CLOSED = 24 * 3600.0         # (d)
PULSE_SPM, PULSE_S = 10.0, 30.0
DI_THRESHOLD = 0.1
BISECT_TOL = 1e-4

FIELDS = ["kind", "param", "value", "F_couple", "rho_xe_full",
          "trim_max_diff", "re", "im", "doubling_h", "period_h", "label",
          "ol_absDI_after_pulse", "ol_absDI_6h", "ol_peak_absDI", "ol_t_exceed_h",
          "ol_t_exceed_half_h", "ol_t_reached_h",
          "cl_max_absDI", "cl_final_DI", "cl_left_band", "cl_rod_travel_steps",
          "cl_t_reached_h", "lo", "hi"]


def make_plant(F: float, xe: float) -> Plant:
    # The grid deliberately goes below the stability boundary; the warning
    # Plant raises there is the thing being measured, not news.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return Plant(Params(F_couple=F, rho_xe_full=xe))


def rightmost(plant: Plant, x0, u0) -> complex:
    """Rightmost eigenvalue, ignoring the structural integrators at zero."""
    ev = np.linalg.eigvals(linearize(plant, x0, u0)[0])
    ev = ev[np.abs(ev) > 1e-12]
    lam = ev[np.argmax(ev.real)]
    return complex(lam.real, abs(lam.imag))


def classify(lam: complex) -> str:
    if lam.real <= 0.0:
        return "stable"
    return "unstable_osc" if lam.imag > 0.0 else "unstable_real"


def linear_mode(F: float, xe: float, x_ref) -> dict:
    plant = make_plant(F, xe)
    x0, u0, _ = trim(plant, 1.0, di_target=0.0)
    diff = float(np.max(np.abs(x0 - x_ref)))
    if not diff < 1e-12:                                   # (a) -- the guard
        raise SystemExit(
            f"TRIM MOVED: F_couple={F}, rho_xe_full={xe} shifted the symmetric "
            f"100 % trim by {diff:.3e}.  Something other than the swept "
            "parameter changed; every later number would measure the wrong "
            "thing.  Stopping.")
    lam = rightmost(plant, x0, u0)
    return dict(F_couple=F, rho_xe_full=xe, trim_max_diff=diff,
                re=lam.real, im=lam.imag,
                doubling_h=(np.log(2) / lam.real / 3600 if lam.real > 0 else np.inf),
                period_h=(2 * np.pi / lam.imag / 3600 if lam.imag > 0 else np.inf),
                label=classify(lam))


def open_loop_tilt(F: float, xe: float) -> dict:
    """(c): bare plant, no controllers at all, after a differential rod pulse."""
    def pulse(sign):
        return lambda t, sig: sign * PULSE_SPM if t < PULSE_S else 0.0
    loop = ClosedLoop(make_plant(F, xe),
                      [Manual("vrod_M", pulse(+1.0), accumulate=True),
                       Manual("vrod_AO", pulse(-1.0), accumulate=True)])
    d = loop.run(T_OPEN, n_out=2000, max_step=10.0).df
    a = np.abs(d["DI"].to_numpy())
    a = a[np.isfinite(a)]
    th = d["t_h"].to_numpy()[:len(a)]
    first = lambda lim: (float(th[np.argmax(a > lim)]) if np.any(a > lim) else np.inf)
    return dict(ol_absDI_after_pulse=float(np.interp(2 * PULSE_S / 3600, th, a)),
                ol_absDI_6h=float(np.interp(6.0, th, a)),
                ol_peak_absDI=float(a.max()),
                ol_t_exceed_h=first(DI_THRESHOLD),
                ol_t_exceed_half_h=first(0.5),
                ol_t_reached_h=float(th[-1]))


def closed_loop_cost(F: float, xe: float) -> dict:
    """(d): the standard load-follow with the shipped AO band controller."""
    loop = turbine_leading(make_plant(F, xe), demand=ramp(1.0, 0.5, hold=4 * 3600),
                           ao_band=BAND)
    d = loop.run(T_CLOSED, n_out=6000).df
    di = d["DI"].to_numpy()
    speed = np.abs(d["u_vrod_M"].to_numpy()) + np.abs(d["u_vrod_AO"].to_numpy())
    travel = float(np.trapezoid(speed, d["t"].to_numpy()) / 60.0)   # spm -> steps
    return dict(cl_max_absDI=float(np.max(np.abs(di))), cl_final_DI=float(di[-1]),
                cl_left_band=bool(np.max(np.abs(di)) > BAND),
                cl_rod_travel_steps=travel,
                cl_t_reached_h=float(d["t_h"].iloc[-1]))


def bisect_xe(lo: float, hi: float, on_lo_side, x_ref) -> tuple:
    """Shrink [lo, hi] in rho_xe_full until it is narrower than BISECT_TOL/8."""
    while abs(hi - lo) > BISECT_TOL / 8:
        mid = 0.5 * (lo + hi)
        if on_lo_side(linear_mode(F_DEFAULT, mid, x_ref)):
            lo = mid
        else:
            hi = mid
    return lo, hi


def sweep(param: str, grid, closed, x_ref, quick: bool) -> list:
    rows = []
    for v in grid:
        F, xe = (v, XE_DEFAULT) if param == "F_couple" else (F_DEFAULT, v)
        row = dict(kind="sweep", param=param, value=v, **linear_mode(F, xe, x_ref))
        if not quick:
            row.update(open_loop_tilt(F, xe))
            if v in closed:
                row.update(closed_loop_cost(F, xe))
        rows.append(row)
        print(f"  {param:11s} = {v:7.3f}   lam = {row['re']:+.3e} "
              f"{'+/- %.3e j' % row['im'] if row['im'] else '(real)        '}   "
              f"{row['label']:13s}"
              + ("" if quick else f"  open |DI| {row['ol_peak_absDI']:.3f}"
                 + (f"  closed |DI| {row['cl_max_absDI']:.4f}"
                    if "cl_max_absDI" in row else "")))
    return rows


def draw(rows, param: str, default: float, fname: Path, xlabel: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = Result.COLORS
    ref = lambda ax, y, label=None: Result.setpoint(None, ax, y, label)
    x = np.array([r["value"] for r in rows])
    col = lambda k: np.array([r.get(k, np.nan) for r in rows], dtype=float)

    fig, axs = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    (a, b), (cc, d) = axs

    a.plot(x, col("re") * 1e5, "o-", color=c[0], lw=1.5)
    ref(a, 0.0, "stability boundary")
    a.set_ylabel(r"Re $\lambda_{max}$  (1e-5 /s)")
    a.set_title("growth rate of the axial mode", fontsize=10)

    per = col("period_h")
    per[~np.isfinite(per)] = np.nan
    b.plot(x, per, "o-", color=c[1], lw=1.5)
    b.set_ylabel("oscillation period (h)")
    b.set_title("period (no point = real pole, no oscillation)", fontsize=10)

    cc.plot(x, col("ol_peak_absDI"), "o-", color=c[2], lw=1.5)
    ref(cc, DI_THRESHOLD, f"|DI| = {DI_THRESHOLD}")
    cc.set_ylabel("peak open-loop |DI| in 12 h")
    cc.set_title("no controller, after a rod pulse", fontsize=10)

    d.plot(x, col("cl_max_absDI"), "o-", color=c[3], lw=1.5)
    ref(d, BAND, f"band = {BAND}")
    d.set_ylabel("closed-loop max |DI| in 24 h")
    d.set_title("load-follow with AxialOffsetBand", fontsize=10)
    d.set_ylim(0.0, 1.5 * BAND)          # from zero: the spread is ~1e-4

    pad = 0.04 * (x.max() - x.min())
    for ax in axs.flat:
        ax.set_xlim(x.min() - pad, x.max() + pad)
        ax.axvline(default, color="#8a8984", lw=1.0, ls=":", zorder=0)
        ax.set_xlabel(xlabel)
        ax.grid(alpha=0.25)
    a.annotate("default", (default, a.get_ylim()[1]), fontsize=8,
               color="#8a8984", ha="left", va="top",
               xytext=(3, -3), textcoords="offset points")
    fig.suptitle(f"Sensitivity to {param}  (other parameter at its default; "
                 "100 % symmetric trim)", fontsize=11)
    fname.parent.mkdir(exist_ok=True)
    fig.savefig(fname, dpi=120)
    plt.close(fig)
    print(f"  -> {fname.relative_to(HERE.parent)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quick", action="store_true",
                    help="(a) and (b) only; writes no files")
    ap.add_argument("--F-couple", type=float, default=None, metavar="FLOAT",
                    help=f"axial diffusion coupling, 1/s (default {F_DEFAULT})")
    ap.add_argument("--rho-xe", type=float, default=None, metavar="FLOAT",
                    help=f"xenon worth at full power, dk/k (default {XE_DEFAULT})")
    args = ap.parse_args()
    t0 = time.time()

    x_ref, _, res = trim(Plant(), 1.0, di_target=0.0)
    print(f"reference trim residual {res:.2e}")

    if args.F_couple is not None or args.rho_xe is not None:
        F = F_DEFAULT if args.F_couple is None else args.F_couple
        xe = XE_DEFAULT if args.rho_xe is None else args.rho_xe
        print(f"single point: F_couple = {F} 1/s, rho_xe_full = {xe} dk/k")
        row = linear_mode(F, xe, x_ref)
        if not args.quick:
            row.update(open_loop_tilt(F, xe))
            row.update(closed_loop_cost(F, xe))
        for k, v in row.items():
            print(f"  {k:22s} {v}")
        return 0

    print(f"F_couple sweep (rho_xe_full = {XE_DEFAULT}):")
    rows_F = sweep("F_couple", F_GRID, F_CLOSED, x_ref, args.quick)
    print(f"rho_xe_full sweep (F_couple = {F_DEFAULT}):")
    rows_X = sweep("rho_xe_full", XE_GRID, XE_CLOSED, x_ref, args.quick)

    print("transitions in rho_xe_full (bisection):")
    s_lo, s_hi = bisect_xe(-0.014, -0.018, lambda r: r["re"] < 0, x_ref)
    c_lo, c_hi = bisect_xe(-0.028, -0.034, lambda r: r["im"] > 0, x_ref)
    print(f"  stability boundary     between {s_lo:.5f} and {s_hi:.5f}")
    print(f"  complex -> real pole   between {c_lo:.5f} and {c_hi:.5f}")
    trans = [dict(kind="transition", param="rho_xe_full", label="stability_boundary",
                  F_couple=F_DEFAULT, lo=s_lo, hi=s_hi),
             dict(kind="transition", param="rho_xe_full", label="complex_to_real",
                  F_couple=F_DEFAULT, lo=c_lo, hi=c_hi)]

    if not args.quick:
        import csv
        out = HERE / "sensitivity_results.csv"
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, restval="")
            w.writeheader()
            w.writerows(rows_F + rows_X + trans)
        print(f"  -> {out.relative_to(HERE.parent)}")
        draw(rows_F, "F_couple", F_DEFAULT, HERE / "figures" / "sensitivity_F.png",
             "F_couple (1/s)")
        draw(rows_X, "rho_xe_full", XE_DEFAULT,
             HERE / "figures" / "sensitivity_xe.png", "rho_xe_full (dk/k)")
    print(f"wall clock {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
