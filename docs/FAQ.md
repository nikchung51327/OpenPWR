# FAQ

Short answers, each pointing at the document that has the evidence.

| question | answer |
|---|---|
| **How was `F_couple` picked?** | It is [L]'s formula `F = 4·d·v_s/h²` evaluated with `d ≈ 0.0085 m`, `v_s ≈ 2200 m/s` and `h = 3.66 m`, which gives 5.58 1/s, rounded to 5.6. [L] prints the formula but none of the three inputs, so the inputs are standard textbook values rather than [L]'s. It is not calibrated to an oscillation period. See [VALIDATION_AND_CONSTRAINTS.md](VALIDATION_AND_CONSTRAINTS.md) §3.5. |
| **How was the xenon worth picked?** | `rho_xe_full = −0.028` Δk/k (2800 pcm) is the standard literature figure for equilibrium xenon worth in a PWR at full power. [L] names the coefficient but prints no value, and [V] has no xenon at all. See [VALIDATION_AND_CONSTRAINTS.md](VALIDATION_AND_CONSTRAINTS.md) §3.6. |
| **Which of the two matters more?** | The xenon worth, by a wide margin. A 25× change in `F_couple` moves the doubling time of the axial mode from 3.18 to 4.55 h and changes nothing qualitative. A 4.5× change in `rho_xe_full` takes the same mode from stable (below about 0.0149 in magnitude), through unstable and oscillatory, to unstable and monotonic (beyond about 0.0315). See [SENSITIVITY.md](SENSITIVITY.md). |
| **I changed `rho_xe_full` and `DI` just sits flat. Is the model broken?** | No. Below a magnitude of about 0.0149 the axial xenon mode is stable, so there is nothing to diverge. `Plant()` raises a `RuntimeWarning` when the value is under 0.015. That boundary was measured at the symmetric 100 % trim with the default `F_couple` and has not been checked elsewhere. |
