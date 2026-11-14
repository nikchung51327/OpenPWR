#!/usr/bin/env python3
"""Smoke test: does the restructured repo still work?

Not a validation — `validation/validate_vajpayee.py` is that, and it takes
seconds per case. This answers a narrower question: after moving files around,
does the package import, build, trim and integrate, and did anything get left
pointing at the old layout?

Run from anywhere:

    python tests/smoke_test.py

Exit code 0 if every check passes, 1 otherwise. Each check prints its own line,
so a failure tells you which one without reading a traceback.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

# tests/ is not the repo root, and running a script puts the SCRIPT's directory
# on sys.path, not the root.  Without this, `import pwr_plant` fails.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_results: list[tuple[str, bool, str]] = []


def check(label: str):
    """Decorator: run a check, record pass/fail, never let it abort the run."""
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            _results.append((label, True, f"{detail}  ({time.time()-t0:.2f}s)"))
        except Exception as exc:                                  # noqa: BLE001
            line = traceback.extract_tb(exc.__traceback__)[-1].lineno
            _results.append((label, False,
                             f"{type(exc).__name__}: {exc}  [line {line}]"))
        return fn
    return wrap


# ---------------------------------------------------------------------------
# 1.  Layout
# ---------------------------------------------------------------------------
@check("layout: expected files are where the structure says")
def _layout():
    expected = [
        "pwr_plant/__init__.py", "pwr_plant/model.py",
        "validation/validate_vajpayee.py",
        "validation/figures/fig10.png", "validation/figures/fig11.png",
        "docs/QUICKSTART.md", "docs/API_REFERENCE.md",
        "docs/MORE_CONTROL_EXAMPLES.md", "docs/VALIDATION_AND_CONSTRAINTS.md",
        "requirements.txt", "README.md",
    ]
    missing = [p for p in expected if not (ROOT / p).exists()]
    if missing:
        raise FileNotFoundError("missing: " + ", ".join(missing))
    return f"{len(expected)} paths present"


@check("layout: no file still refers to the pre-move module name")
def _no_stale_refs():
    """The rename is the thing most likely to be left half-done."""
    stale, skip = [], {".git", ".venv", "__pycache__", ".ipynb_checkpoints"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in {".py", ".md", ".ipynb", ".txt", ".cfg", ".toml"}:
            continue
        if set(p.relative_to(ROOT).parts) & skip or p.name in {"smoke_test.py", "CLAUDE.md", "changes_log.md"}:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "pwr_two_point_plant" in body:
            n = sum("pwr_two_point_plant" in ln for ln in body.splitlines())
            stale.append(f"{p.relative_to(ROOT)} ({n})")
    if stale:
        raise AssertionError("still importing the old name: " + "; ".join(stale))
    return "no references to pwr_two_point_plant*"


# ---------------------------------------------------------------------------
# 2.  The package API the restructure promised
# ---------------------------------------------------------------------------
@check("import: `from pwr_plant import *` exposes the public names")
def _flat_import():
    ns: dict = {}
    exec("from pwr_plant import *", ns)
    want = ["Plant", "Params", "Config", "ClosedLoop", "Controller", "trim",
            "linearize", "IU", "U_NAMES", "OUTPUT_NAMES", "ramp", "step",
            "GridDemand", "TurbineSpeedPI", "RodsOnTavg", "AxialOffsetBand"]
    missing = [n for n in want if n not in ns]
    if missing:
        raise ImportError("not re-exported by __init__: " + ", ".join(missing))
    return f"{len(want)} names"


@check("import: `pwr_plant.model` is still reachable, and is the same module")
def _deep_import():
    import pwr_plant
    from pwr_plant.model import Plant as DeepPlant
    if pwr_plant.Plant is not DeepPlant:
        raise AssertionError(
            "pwr_plant.Plant and pwr_plant.model.Plant are different objects — "
            "the package is being imported twice under two names")
    return "same object via both paths"


# ---------------------------------------------------------------------------
# 3.  The model itself
# ---------------------------------------------------------------------------
@check("model: Plant builds with the expected shape")
def _build():
    from pwr_plant import Plant, U_NAMES
    p = Plant()
    if (p.n, p.m) != (53, 8):
        raise AssertionError(f"expected 53 states / 8 inputs, got {p.n} / {p.m}")
    if U_NAMES[0] != "vrod_M" or U_NAMES[-1] != "mdot_sur":
        raise AssertionError(f"input order changed: {U_NAMES}")
    return f"{p.n} states, {p.m} inputs"


@check("model: trim converges to an equilibrium")
def _trim():
    from pwr_plant import Plant, trim
    _, _, residual = trim(Plant(), 1.0)
    if not residual < 1e-10:
        raise AssertionError(f"trim residual {residual:.2e}, expected < 1e-10")
    return f"residual {residual:.1e}"


@check("model: a steady run stays steady")
def _steady():
    from pwr_plant import Plant, ClosedLoop, trim
    plant = Plant()
    x0, u0, _ = trim(plant, 1.0)
    d = ClosedLoop(plant, [], x0=x0, u0=u0).run(300, n_out=100).df
    drift = abs(float(d["Pn"].iloc[-1]) - 1.0)
    if not drift < 1e-6:
        raise AssertionError(f"Pn drifted {drift:.2e} from an equilibrium start")
    return f"Pn drift {drift:.1e}"


@check("model: the two free parameters can be overridden through Params")
def _free_params():
    """F_couple and rho_xe_full are ordinary Params fields.  Keep that path
    live, and keep the symmetric 100 % trim independent of both."""
    import numpy as np
    from pwr_plant import Plant, Params, trim
    x_ref, _, _ = trim(Plant(), 1.0)
    plant = Plant(Params(F_couple=12.0, rho_xe_full=-0.034))
    x0, _, residual = trim(plant, 1.0)
    if not residual < 1e-10:
        raise AssertionError(f"trim residual {residual:.2e}, expected < 1e-10")
    moved = float(np.max(np.abs(x0 - x_ref)))
    if not moved < 1e-12:
        raise AssertionError(f"override moved the symmetric trim by {moved:.2e}")
    return f"residual {residual:.1e}, trim moved {moved:.1e}"


@check("model: rod sign conventions are the documented way round")
def _rod_signs():
    """Mrod drives the bottom half and lowers DI; AOrod the top and raises it.

    This is checked because the default `rod_map` was the transpose until
    2026-10-11, and nothing about a wrong map raises an error — the loops just
    quietly drive the wrong way.
    """
    from pwr_plant import Plant, ClosedLoop, Manual, trim
    plant = Plant()
    x0, u0, _ = trim(plant, 1.0)
    out = {}
    for rod in ("vrod_M", "vrod_AO"):
        r = ClosedLoop(plant, [Manual(rod, lambda t, s: 5.0 if t > 20 else 0.0)],
                       x0=x0, u0=u0).run(300)
        out[rod] = (float(r["Pn"][-1]) - 1.0, float(r["DI"][-1]))
    (m_pn, m_di), (a_pn, a_di) = out["vrod_M"], out["vrod_AO"]
    if not (m_pn > 0 and a_pn > 0):
        raise AssertionError(f"withdrawing a rod should raise power: {out}")
    if not (m_di < 0 < a_di):
        raise AssertionError(
            f"expected vrod_M to LOWER DI and vrod_AO to RAISE it, got {out}")
    return f"Mrod dDI {m_di:+.4f}, AOrod dDI {a_di:+.4f}"


@check("model: a closed loop runs and holds its setpoints")
def _closed_loop():
    from pwr_plant import (Plant, ClosedLoop, GridDemand, TurbineSpeedPI,
                           RodsOnTavg, AxialOffsetBand, ramp, trim)
    plant = Plant()
    x0, u0, _ = trim(plant, 1.0)
    d = ClosedLoop(
        plant,
        [GridDemand(), TurbineSpeedPI(), RodsOnTavg(), AxialOffsetBand(band=0.03)],
        demand=ramp(start=1.0, target=0.9, t_start=600.0,
                    ramp_time=600.0, hold=1800.0),
        x0=x0, u0=u0,
    ).run(4800, n_out=800, max_step=2.0).df
    w_dev = float((d["w_tur"] - 60.0).abs().max())
    di_pk = float(d["DI"].abs().max())
    if not w_dev < 0.2:
        raise AssertionError(f"governor let speed move {w_dev:.3f} Hz")
    if not di_pk < 0.05:
        raise AssertionError(f"axial band let |DI| reach {di_pk:.4f}")
    return f"speed within {w_dev:.4f} Hz, |DI| peak {di_pk:.4f}"


# ---------------------------------------------------------------------------
# 4.  The validation script, from its new home
# ---------------------------------------------------------------------------
@check("validation: the script runs from BOTH the repo root and validation/")
def _validation_runs():
    """Run it as a subprocess, the way a person actually invokes it.

    This is deliberately not an `import` with sys.path pre-patched — that is
    what the first version of this test did, and it masked a real bug.
    `python validation/validate_vajpayee.py` puts *validation/* on sys.path,
    not the repo root, so the script cannot see `pwr_plant` from EITHER
    directory unless it inserts the root itself.
    """
    import subprocess
    for cwd, argv in ((ROOT, ["validation/validate_vajpayee.py", "--help"]),
                      (ROOT / "validation", ["validate_vajpayee.py", "--help"])):
        r = subprocess.run([sys.executable, *argv], cwd=cwd,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-1:]
            raise RuntimeError(f"failed when run from {cwd.name or 'repo root'}/"
                               f": {' '.join(tail)}")
    return "imports cleanly from both"


@check("validation: one case runs end to end")
def _one_case():
    """Case B only — the cheapest real integration through the full plant."""
    import importlib.util
    path = ROOT / "validation" / "validate_vajpayee.py"
    spec = importlib.util.spec_from_file_location("_vv_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_vv_smoke"] = mod
    spec.loader.exec_module(mod)
    if len(mod.CASES) != 4:
        raise AssertionError(f"expected 4 cases, found {len(mod.CASES)}")
    from pwr_plant import Plant, Config, Params, ClosedLoop, trim
    plant = Plant(Params(), Config(two_point=False, xenon=False))
    x0, u0, _ = trim(plant, 1.0)
    tag, _desc, builder = mod.CASES[1]
    d = ClosedLoop(plant, builder(plant, u0), x0=x0, u0=u0).run(
        mod.T_END, n_out=200, max_step=mod.MAX_STEP[tag]).df
    end = float(d["Pn"].iloc[-1])
    if not 1.01 < end < 1.03:                 # [V] Fig. 10a settles near 1.018
        raise AssertionError(f"{tag} ended at Pn = {end:.4f}, expected ~1.018")
    return f"{tag}: Pn -> {end:.4f}"


@check("validation: figures are written beside the script, not the CWD")
def _fig_dir():
    body = (ROOT / "validation" / "validate_vajpayee.py").read_text()
    if "validation_fig10" in body:
        raise AssertionError("still writing the old validation_fig10*.png names")
    if "__file__" not in body:
        raise AssertionError("figure path is not resolved from __file__, so the "
                             "output location depends on the working directory")
    figs = ROOT / "validation" / "figures"
    have = sorted(p.name for p in figs.glob("fig1*.png")) if figs.is_dir() else []
    if not {"fig10.png", "fig11.png"} <= set(have):
        raise AssertionError(f"validation/figures/ holds {have}")
    return f"{len(have)} figures present"


# ---------------------------------------------------------------------------
def main() -> int:
    print(f"smoke test — {ROOT}\n")
    width = max(len(l) for l, _, _ in _results)
    failed = 0
    for label, ok, detail in _results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<{width}}  {detail}")
        failed += not ok
    print()
    if failed:
        print(f"{failed} of {len(_results)} checks FAILED")
        return 1
    print(f"all {len(_results)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
