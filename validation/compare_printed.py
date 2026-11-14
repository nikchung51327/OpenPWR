#!/usr/bin/env python3
"""
compare_printed.py -- run [V]'s four open-loop cases twice: once with the
shipped parameters, once with `Params.as_printed()`, i.e. every flagged value
restored to Table 1 / eq 50 exactly as the paper prints them.

The point is to make the six deviations auditable.  For each one, either the
printed value works (and the shipped deviation was unnecessary) or it does not
(and the deviation was load-bearing).  Nothing here is a judgement call: the
model either integrates or it does not, and either lands on [V]'s own Figs. 10
and 11 or it does not.

    python compare_printed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# `python validation/compare_printed.py` puts validation/ on sys.path, not the
# repo root -- so pwr_plant is invisible without this, from ANY directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pwr_plant import (ClosedLoop, Config, Params, Plant, trim,
                       IU, Manual)
from validate_vajpayee import (CASES, PAPER, T_END, run_case_A,
                               total_reactivity)

CFG = Config(two_point=False, xenon=False)
RULE = "=" * 78


# ---------------------------------------------------------------------------
def geometry_check(p: Params, tag: str) -> None:
    """[V] eq 28: the pressurizer is `l` long and holds `lw` of water."""
    frac = p.lw0 / p.l_pzr
    verdict = "OK" if 0.0 < frac < 1.0 else "IMPOSSIBLE"
    print(f"  {tag:9s} lw0/l = {p.lw0:7.4f} / {p.l_pzr:7.4f} = {frac:6.3f}"
          f"   {verdict}")
    if frac >= 1.0:
        print(f"  {'':9s}   -> steam volume = {1.0 - frac:+.3f} of the vessel")


def try_trim(p: Params, tag: str):
    """Trim, reporting rather than raising."""
    try:
        plant = Plant(p, CFG)
        x0, u0, res = trim(plant, 1.0)
        ok = res < 1e-6 and np.all(np.isfinite(x0))
        print(f"  {tag:9s} trim residual {res:.3e}   "
              f"{'OK' if ok else 'FAILED TO CONVERGE'}")
        return (plant, x0, u0) if ok else (plant, None, None)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {tag:9s} trim RAISED {type(exc).__name__}: "
              f"{str(exc)[:60]}")
        return None, None, None


def run_cases(plant, x0, u0):
    """Return {case tag: df} or {} if anything blows up."""
    out = {}
    for tag, _desc, builder in CASES:
        try:
            if builder is None:
                # Case A has no input builder: it is a step in the rod
                # reactivity STATE, run by validate_vajpayee.run_case_A.
                d = run_case_A(plant, x0, u0, T_END, 600)
            else:
                loop = ClosedLoop(plant, builder(plant, u0), x0=x0, u0=u0)
                d = loop.run(T_END, n_out=600, max_step=0.25).df
            if not np.all(np.isfinite(d[["Pn", "pp", "ps"]].to_numpy())):
                print(f"    {tag}: produced non-finite states")
                continue
            d["_Tf"] = 0.5 * (d["Tf_h1"] + d["Tf_h2"])   # [V] has one fuel node
            out[tag] = d
        except Exception as exc:                              # noqa: BLE001
            print(f"    {tag}: RAISED {type(exc).__name__}: {str(exc)[:55]}")
    return out


def score(runs) -> tuple:
    """Direction agreement against PAPER, as validate_vajpayee.compare does.

    SCOPE: this is a FINAL STEADY-STATE comparison and nothing else.  Each
    trace is reduced to `end - start`, and the test is whether that net change
    has the same sign as the paper's (or is near zero where the paper is flat).

    It says nothing about the path taken.  Peak value, overshoot, settling time
    and ringing are all invisible to it -- eq 34 as printed oscillates six times
    on the way to the same endpoint and scores identically.  See
    VALIDATION_AND_CONSTRAINTS.md sections 2.4 and 3.2.
    """
    agree = total = 0
    for col, ref in PAPER.items():
        scale = max(abs(ref[k] - ref["start"]) for k in "ABCD")
        for tag in ("Case A", "Case B", "Case C", "Case D"):
            if tag not in runs:
                total += 1
                continue
            d = runs[tag]
            dm = d[col].iloc[-1] - d[col].iloc[0]
            dp = ref[tag.split()[-1]] - ref["start"]
            flat = abs(dp) < 0.05 * scale if scale > 0 else True
            ok = (abs(dm) < 0.05 * scale) if flat else (np.sign(dm) == np.sign(dp))
            agree += ok
            total += 1
    return agree, total


def pressure_table(a, b) -> None:
    """The variable the whole exercise turns on."""
    print(f"\n  {'case':7s} {'paper':>9s} {'shipped':>12s} {'as printed':>14s}")
    for tag in ("Case A", "Case B", "Case C", "Case D"):
        k = tag.split()[-1]
        pe = PAPER["pp"][k]
        sa = f"{a[tag]['pp'].iloc[-1]:.3f}" if tag in a else "--"
        sb = f"{b[tag]['pp'].iloc[-1]:.3f}" if tag in b else "--"
        print(f"  {tag:7s} {pe:9.3f} {sa:>12s} {sb:>14s}")


# ---------------------------------------------------------------------------
def eq50_literal() -> None:
    """[V] eq 50 taken at face value, at his own rod speed limit."""
    print("\n" + RULE)
    print("EQUATION 50, AT THE PAPER'S OWN 72 spm DRIVE LIMIT")
    print(RULE)
    p_ship, p_lit = Params(), Params.as_printed()
    for tag, p in (("shipped", p_ship), ("as printed", p_lit)):
        rate = p.G_dkk_per_step * p.rod_spm_to_per_s * 72.0
        print(f"  {tag:11s} drho/dt = {rate:9.4f} dk/k per s "
              f"= {rate / p.beta:8.2f} $ per s")
    print(f"\n  beta = {p_ship.beta:.6f}.  Prompt critical at rho = beta, i.e. $1.")
    t_pc = p_ship.beta / (p_lit.G_dkk_per_step * p_lit.rod_spm_to_per_s * 72.0)
    print(f"  As printed, the drive reaches prompt critical in {t_pc:.3f} s of")
    print(f"  continuous withdrawal.  [V]'s own Fig. 12b shows the rod loop")
    print(f"  making ~12-cent corrections, which it cannot do at this gain.")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(RULE)
    print("PRESSURIZER GEOMETRY, [V] eq 28")
    print(RULE)
    geometry_check(Params(), "shipped")
    geometry_check(Params.as_printed(), "printed")

    print("\n" + RULE)
    print("TRIM")
    print(RULE)
    pa, xa, ua = try_trim(Params(), "shipped")
    pb, xb, ub = try_trim(Params.as_printed(), "printed")

    print("\n" + RULE)
    print("THE FOUR CASES")
    print(RULE)
    print("  shipped:")
    ra = run_cases(pa, xa, ua) if xa is not None else {}
    print("  as printed:")
    rb = run_cases(pb, xb, ub) if xb is not None else {}

    print("\n" + RULE)
    print("SCORE against [V] Figs. 10 and 11")
    print("  (final steady-state values only: sign of end-minus-start,\n   not peak, overshoot or settling time)")
    print(RULE)
    for tag, r in (("shipped", ra), ("as printed", rb)):
        a, t = score(r)
        print(f"  {tag:11s} {a:2d}/{t} direction agreements")
    if ra or rb:
        pressure_table(ra, rb)

    # ----------------------------------------------------------------- #
    # Which of the six is load-bearing?  Flip exactly one at a time.
    # ----------------------------------------------------------------- #
    print("\n" + RULE)
    print("ABLATION -- shipped defaults with ONE value restored to the paper")
    print(RULE)
    ABL = [
        ("pzr partials",  dict(pzr_partial_scale=1.0)),
        ("lw0 = 28.06",   dict(lw0=28.06)),
        ("condenser h",   dict(h_cow=69.74, h_lp=1036.0)),
        ("Ctg = 2.0481",  dict(use_printed_Ctg=True)),
        ("eq 50 literal", dict(rod_spm_to_per_s=1.0)),
    ]
    base, _ = score(ra)
    print(f"  {'(shipped)':16s} {base:2d}/40")
    for label, kw in ABL:
        pl = Params(**kw)
        try:
            plant = Plant(pl, CFG)
            x0, u0, res = trim(plant, 1.0)
            r = run_cases(plant, x0, u0) if res < 1e-6 else {}
            s, _ = score(r)
            delta = s - base
            mark = "" if delta == 0 else f"   <-- {delta:+d}"
            print(f"  {label:16s} {s:2d}/40{mark}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  {label:16s} RAISED {type(exc).__name__}")

    eq50_literal()
