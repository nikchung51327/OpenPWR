# CLAUDE.md — repo context

Read this before touching anything. It exists so that an agent working in this
repo can answer *"what is this model, what is it for, and what is it not valid
for"* correctly, without re-deriving it from the source.

Authoritative documents, in order of precedence:

1. `docs/VALIDATION_AND_CONSTRAINTS.md` — every claim about what is validated,
   what deviates from the papers, and what the model may not be used for. **If
   this file and anything else disagree, this file wins.**
2. `pwr_plant/model.py` comments — provenance of individual numbers.
3. `docs/QUICKSTART.md`, `docs/API_REFERENCE.md`, `docs/FAQ.md` — how to use it.
4. This file — the summary. Do not treat it as a source; it is a map.

---

## 1. What this is

A **control-research testbed for a pressurized water reactor**, built to study
**axial offset control** — keeping the vertical power distribution flat while
the plant follows load.

It is a transplant of two published models:

| key | paper | what it supplies |
|---|---|---|
| **[V]** | Vajpayee, Becerra, Bausch, Deng, Shimjith, Arul (2020), *Nucl. Eng. Des.* 370, 110901 | the whole plant: loop, steam generator, pressurizer, turbine, governor, sensors — and **every numerical parameter** |
| **[L]** | Li (2014), *Ann. Nucl. Energy* 68, 193–203 | the two-point axial core: point kinetics + iodine/xenon per axial half, with diffusion coupling between them |
| **[K]** | Kerlin, Katz, Thakkar, Strange (1976), *Nucl. Technol.* 30(3) | H. B. Robinson plant measurements, used only for validation |

[V]'s single-point core is **replaced** by two Mann stacks in series, one per
axial half. Everything outside the core is [V]'s, unchanged. The joint is two
substitutions: core exit feeds the loop (`Tc2_h2` → [V] eq 8), and the loop
feeds the core inlet (`Trxi` → [L]'s `T1Cin`).

That series arrangement is the thing people get wrong about this model: **the
two halves are not symmetric.** Half 1 (bottom) is cooled by loop water; half 2
(top) is cooled by water that has already passed through half 1.

Outputs: `Pn = (Pr1 + Pr2)/2` (total power) and `DI = (Pr2 − Pr1)/2` (axial
power difference — positive means top-peaked).

53 states, 8 inputs. 24 of the states are the core (12 per half).

---

## 2. What it is for

**Load-following inside the normal operating band.** Specifically:

- power manoeuvres (ramps, steps, daily load cycles)
- average-coolant-temperature (`Tavg`) programme control
- axial offset control, including the unstable axial xenon mode
- multivariable and sampled-time control design: the two rod groups against
  `Pn` and `DI` is a genuine 2×2 problem with a clean modal split
  (RGA λ₁₁ = 0.975)

It is a good testbed for these because the axial instability is real, the two
rod loops genuinely interact, and the plant around the core is validated.

---

## 3. What it is NOT valid for — state these when asked

### 3.1 Anything involving a safety limit

There is **no reactor trip logic, no overtemperature-ΔT or overpower-ΔT
setpoint, no DNBR, no peaking factor, no linear heat rate, no rod insertion
limit, no withdrawal interlock.**

> **The model cannot be used to argue that a controller respects a safety
> limit, because it contains no safety limits.** A controller that drives it
> somewhere catastrophic is indistinguishable from one that does not.

Say this plainly. Do not soften it.

### 3.2 Anything involving shutdown or a trip

No decay heat. Power follows the neutron kinetics to zero, where a real
reactor still has ~7 % of full power seconds after shutdown, decaying over
days. Every shutdown, trip, or large downpower transient is wrong in the tail.

### 3.3 Long runs without an axial offset controller

The axial xenon mode is **unstable by design** — at the default parameters the
linearisation at 100 % has a right-half-plane pair at

```
lambda = +5.66e-5 +/- 4.13e-5 j  /s     doubling 3.40 h, period 42.2 h
```

From an initial tilt of 0.034, `|DI|` reaches 0.58 in six hours and 0.87
within twelve, and never settles. Any run longer than a few hours **needs** `AxialOffsetBand` or
equivalent, or you are watching a divergence, not a transient.

### 3.4 Plant systems that are absent

- **Feedwater / SG level.** `T_fw` is an input; `mdot_fw` is not, and there is
  no SG downcomer level state. No three-element feedwater control is possible.
- **Boron / CVCS boration–dilution.** No boron state. ([L] excludes boron
  deliberately, so this omission is shared and intentional.)
- **Steam dump / turbine bypass.** No path around the turbine, so no load
  rejection or turbine trip without a reactor trip.
- **Reactor coolant pump speed.** Primary flow is constant; no RCP coastdown.
- **Primary hydraulics**, SG shrink/swell, U-tube level. The secondary is a
  2-node lump.

### 3.5 Quantitative claims about any real plant

The core *equations* are [L]'s; **every numerical parameter in them is [V]'s**,
because [L]'s Table 1 contains no numbers at all — it is a symbol glossary.
Two further numbers come from neither paper (section 5 below).

So this is a **hybrid**, not any real plant. Quote behaviours, trends, and
closed-loop performance comparisons. Do not quote absolute values as if they
described a specific reactor.

### 3.6 Numerical boundaries

- Linearity holds to about a **12 % step** for 5 % error in `Pn`. Beyond that,
  use a schedule.
- `cond(A) ≈ 1e25`. If you integrate the linear model yourself, **pass the
  Jacobian explicitly**; an implicit solver finite-differencing it returns
  non-finite values.
- `rod_map` is **constant**, so it encodes one fixed assumption about where
  both rod tips sit. Nothing detects a tip crossing the midplane. Fine for
  excursions of tens of steps out of a ~231-step bank; wrong for a full
  withdrawal.
- The pressurizer level loop is **mandatory** under aggressive control, because
  `lw` ([V] eq 28) is a pure integrator with no restoring term.

---

## 4. Validation status — do not overstate this

| what | status |
|---|---|
| [V] plant, eqs 1–52 | implemented; 10 documented deviations, each from a defect in the printed paper |
| [V] open-loop figures 10–11 | **40/40** on the shipped defaults; 37/40 with `--surge`; 30/40 with `--printed` |
| [V] control gains, Table 2 | only the SG-pressure gains transfer. Rod-loop and governor gains do not (eq 50 unit error; 0.16 % implied droop) |
| [L] core, eqs 1–14 | implemented; **no numerical parameter in it is [L]'s** |
| **[L] Tables 2/3 transfer functions** | **never compared against.** The sharpest unused check on the core |
| [L] LQG/**LTR** design | not implemented — LQG only, no recovery, no integrator augmentation |

**The score is final steady-state values only** — `iloc[-1] - iloc[0]` per
channel, compared by sign. It does not look at peak overshoot, settling time,
or ringing. A response that rings six times to the right endpoint scores the
same as one that settles smoothly. Never describe 40/40 as "matches the
paper's figures"; it matches their **endpoints**.

**The asymmetry that matters:** the plant *around* the core is well validated.
The two-point core itself — the part that is new, and the part the research is
about — has never been checked against anything. That is
`VALIDATION_AND_CONSTRAINTS.md` §3.4, and it is the largest open item in the
project after `pzr_partial_scale`.

---

## 5. The two free parameters

Two numbers come from neither paper. They are **not** equally consequential.

### `rho_xe_full = -0.028` dk/k — xenon worth at full-power equilibrium

The standard PWR figure (2800 pcm) from literature. [L] *names* `alpha_X1` but
never prints a value.

**This parameter decides whether the model's central phenomenon exists.**
Measured at the symmetric 100 % trim, rightmost eigenvalue:

| `rho_xe_full` | rightmost eigenvalue | character |
|---|---|---|
| −0.010 | −2.15e-5 ± 5.65e-5 j | **stable** — no axial instability at all |
| −0.014 | −4.09e-6 ± 6.26e-5 j | **stable**, marginally |
| −0.018 | +1.33e-5 ± 6.35e-5 j | unstable, oscillatory |
| **−0.028** | **+5.66e-5 ± 4.13e-5 j** | **unstable, oscillatory — the default** |
| −0.034 | +1.21e-4 (real) | unstable, **monotonic** — no oscillation |
| −0.042 | +2.06e-4 (real) | unstable, monotonic, fast |

Two qualitative transitions sit close to the default: the **stability boundary
at about −0.0149**, below which there is nothing to control, and the
**collision onto the real axis at about −0.0315**, above which the tilt
diverges monotonically instead of oscillating. The default is ~1.9× the
stability boundary and ~11 % short of the oscillatory/monotonic transition.
`Plant.__init__` warns below `XE_STABILITY_WARN = 0.015`.

### `F_couple = 5.6` 1/s — axial diffusion coupling

[L] gives `F = 4·d·v_s/h²` symbolically and never prints `d`, `v_s` or `F`. The
shipped value is that formula with three independently standard inputs:
`d ≈ 0.0085 m`, `v_s ≈ 2200 m/s`, `h = 3.66 m` → 5.5839, rounded to 5.6.
Physically `1/F = 0.179 s` is the neutron diffusion time across the core:
faster than every thermal process, far slower than prompt kinetics.

**It is a weak parameter.** A 25× sweep:

| `F_couple` | rightmost eigenvalue | doubling | period |
|---|---|---|---|
| 1.0 | +6.06e-5 ± 3.61e-5 j | 3.18 h | 48.3 h |
| **5.6** | +5.66e-5 ± 4.13e-5 j | 3.40 h | 42.2 h |
| 25.0 | +4.23e-5 ± 5.38e-5 j | 4.55 h | 32.4 h |

Unstable oscillatory throughout; no qualitative change.

**It is not calibrated to an oscillation period.** The value is the formula
above, and no `F_couple` in 1 → 25 puts the period in a 20–30 h band (it only
moves 48 → 32 h). Do not describe it as tuned.

### Consequence for anyone running the model

Both parameters leave the symmetric 100 % trim **bit-identical** (verified: max
state difference 0.000e+00 across `F_couple` 5.6 → 15 and `rho_xe_full`
−0.028 → −0.040). So the operating point never moves and every difference a
sweep produces is dynamics, not a shifted equilibrium — which is what makes a
sensitivity study clean.

**Read `docs/SENSITIVITY.md` before quoting any `DI` result.** It reports the
sweep over both (`studies/sensitivity.py`) and which statements in the docs are
specific to the defaults.

---

## 6. Conventions that will silently break things

These are the ones that produce plausible-looking wrong answers rather than
errors. Do not change them without reading the surrounding comment.

- **Reactivity is absolute dk/k everywhere inside the integrator.** [V]'s
  nomenclature uses cents and his `G` is cents/step; it is converted on the way
  in. Getting this wrong is a factor of ~100 and the model still looks
  plausible.
- **Rods are velocity inputs, not positions.** `vrod_M` and `vrod_AO` are in
  **steps per minute**, and [V] eq 50 integrates them into reactivity. So a
  *proportional* law on rod speed is *integral* action on the output and tracks
  with no offset. There is no rod position state.
- **Rod commands accumulate.** Write `u[IU["vrod_M"]] += v`, never `=`. That is
  what lets a power/temperature loop and an axial-offset loop share the two rod
  groups. Every other actuator is assigned by exactly one controller.
- **Differential-mode signs are tied to `rod_map`.** Under the default ([L]
  Case 2) `vrod_M` raises `Pn` and **lowers** `DI`; `vrod_AO` raises both. If
  you change `rod_map`, the two lines in `AxialOffsetBand` and `SlidingAO`
  must flip. Nothing detects a mismatch — you get a loop with positive
  feedback that looks like a tuning problem.
- **[L] Case 1 is not Case 2 with `AOrod` frozen.** The cases differ in where
  `Mrod` *starts*, which is a different `rod_map`, not a different command. In
  Case 2, frozen `AOrod` leaves `Mrod` driving the bottom half; in Case 1 it
  drives the top. Opposite halves, opposite sign. Case 1 is
  `Config(rod_map=[[0,0],[1,1]])`.
- **Trim by continuation from the top down.** A cold solve at 30 % will not
  converge. Use `trim_sweep`.
- **Solver defaults are deliberate.** LSODA for the continuous path (it
  switches between stiff and non-stiff itself and copes with the
  discontinuities that dead bands and saturation introduce), BDF for the
  sampled path (restarts ~2.5× faster, and the sampled path restarts once per
  sample). **BDF fails outright on dead bands** — no dead band and both
  finish; add a `Tavg` dead band and BDF raises `ValueError`. Do not "simplify"
  this to one solver.
- **`Ts` is three different things.** `Controller.Ts` is a **sample period in
  seconds**; `sig["Ts"]` is the secondary **saturation temperature in °C**;
  `Params.Ts0` is its nominal value. Check which one you are reading.
- **`"rrod"` must appear in every `freeze()` keep-list that uses a rod
  controller**, or the rod-drive integrator is frozen and `vrod` silently does
  nothing.

---

## 7. How to talk about provenance

A justification written after the fact reads exactly like a real one, and an
error explained that way stops being looked for. So, when writing comments or
docs here:

- **"Chosen because" and "kept because" are different claims.** Use the one you
  can support. A justification found after the fact is a *defence*, not a
  *rationale* — say which.
- If you cannot establish why a deviation exists, write **"origin unknown"**.
  That is a complete, useful statement. A plausible reason written down is
  indistinguishable from a real one, and strictly worse than a blank, because a
  blank invites investigation and a rationale forecloses it.
- Do not promote a symptom to a property. "Did not respond when I tried" is an
  observation; "is uncontrollable" is a claim about the system.
- Say *when* you found something, so a reader can tell original intent from
  later archaeology.

---

## 8. Working rules for this repo

- **Do not create new scripts** unless asked. The working set is:
  `pwr_plant/model.py`, `validation/validate_vajpayee.py`, `docs/QUICKSTART.md`,
  `docs/MORE_CONTROL_EXAMPLES.md`, `docs/API_REFERENCE.md`,
  `docs/VALIDATION_AND_CONSTRAINTS.md`, `docs/SENSITIVITY.md`, `docs/FAQ.md`,
  `README.md`, `requirements.txt`, `pyproject.toml`, `tests/smoke_test.py`,
  `studies/sensitivity.py`.
- **Docs and code comments state the current state only.** What something
  used to be, when it changed, bugs fixed and claims withdrawn all go in
  `changes_log.md` (git-ignored), not in the docs.
- **Figure links in `QUICKSTART.md` and `MORE_CONTROL_EXAMPLES.md` point at
  images that are not in the repo.** The owner is fixing them manually. Leave
  them alone.
- `tests/smoke_test.py` is the fast check — 13 assertions, ~15 s. Run it after
  any change to the model or the layout. It specifically catches stale
  `pwr_two_point_plant` imports, the 53-state/8-input shape, rod sign
  conventions, and `validate_vajpayee.py` being run from the wrong directory.
- `validation/validate_vajpayee.py` is the real check — 40/40, a few minutes.
  Run it before claiming the model still works.
- Treat the two source PDFs as the ground truth for any equation. If you cannot
  check a claim against them, say so rather than asserting it.
