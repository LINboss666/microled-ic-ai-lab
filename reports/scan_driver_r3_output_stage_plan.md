# SCAN-1 R3 — scan output stage **pre-design** (plan + open parameters; nothing simulated here)

Scope as the task book fixes it: connections, polarity, load/voltage and sizing **rationale only**.
**No S3 power-stage deck, no 5 V deck, no output device was simulated or sized.** The R3 control chain
that feeds this stage is reported in `reports/scan_driver_r3_control_chain.md`.

Status: `OUTPUT_STAGE_PRE_DESIGN: PARTIAL`. What is complete — the two candidate routes, the polarity
proof, the load model split and the parameter table below — is written so a reviewer can audit it.
What is missing is not analysis: **`L`/`W`/`m` of any output device cannot be chosen from defined
inputs today**, and choosing them anyway would be the assumption the project forbids.

## 1 Where every number in this plan comes from

| kind | content | how it may be used |
|---|---|---|
| **Teacher / user stated facts** | 1024 columns × 768 rows; 5 µm pixel; **15 µA = the instantaneous current of one *selected*, emitting pixel** (user definition D1, 2026-10-04); 60–100 Hz; scan driver = column driver with high-side switches, data driver = row driver sinking current; SMIC `smic18mmrf` is the fixed process | quotable |
| **Existing architecture assumption** | "one column selected, up to 768 pixels of that column lit at once" | gives `I_SCAN = 768 × 15 µA = 11.52 mA` **as a derived, conditional value**. The direction and the simultaneous-lit count come from the architecture, not from a measured panel |
| **Old draft (spec V1.2) conditions** | 5.0 V output domain, ≤ 0.10 V on-drop, ≥ 0.5 V data-absorption margin, ≤ 0.1 µA per channel off-leakage | **draft conditions, not teacher-issued requirements.** `spec/system_requirements.md` §3 wording was corrected in this round: *"旧方案假设 5 V，最终输出电压待定"*. They may be adopted, and their source must then be named |
| **Readable PDK facts (measured in this project)** | device families present: `n18 p18 n33 p33 nmvt18 nmvt33 nnt18 nnt33 pmvt18`; **`n50`/`p50` model definition count = 0**; DNW variants exist (`n33_dnw_ckt`, `p33_dnw_ckt`, …); legal geometry `n18/p18` lmin 150 nm / wmin 190 nm, `n33/p33` lmin 300–350 nm / wmin 220 nm, wmax 100 µm | quotable, with one limit: **a model name containing `33` is not an absolute rating.** The delivery carries no absolute-maximum / SOA table → `SOA: NO` |
| **R3 measurements (this round)** | `gate33` high **3.3 V**, low **≤ 0.0178 V at 5 pF** and ≤ 2e-08 V at 1 pF; 10–90 % edges **2.025 ns fall / 1.849–2.005 ns rise at 1 pF**, **9.893 ns fall / 9.040 ns rise at 5 pF**; `vdd33` injected peak **0.864…2.042 mA**; the external `core_ok33` low forces `gate33` high **without** touching `Q` or `en` | quotable **for the control chain only** — see §4 for why none of it is an electrode figure |
| **Open items** | final `VSCAN`/`VLED`, LED `Vf` or a usable I–V, scan direction + `N_active`, allowed on-drop / data-node margin, real electrode RC or an explicit course-simulation load | §6 table; each blocks a specific decision |

## 2 What the chain already guarantees about the output stage's input

Derived from the accepted cell bodies and now **measured through the chain** (`r3_write_q1_on`,
`r3_blank_assert`, `r3_external_guard`):

```
selected   (Q=1, blank=0, core_ok33 valid) ->  gate33 = LOW   <- high-side PMOS conducts
idle       (Q=0 or blank=1)                 ->  gate33 = HIGH  <- high-side PMOS off
guard      (core_ok33 = 0, 3.3 V rail valid) ->  gate33 = HIGH  forced, Q and en unchanged
```

So a **source-referenced high-side PMOS needs no gate boost in the 3.3 V domain**: with `S` at `VSCAN`
and `G` at `gate33`, the two measured levels give `VGS = 0 − 3.3 = −3.3 V` (on) and `VGS = 3.3 − 3.3 =
0 V` (off) — the polarity the chain already produces. `gate33` is an active driver in both directions,
not a pull-up: the R3 low plateau is at 1e-08…1.8e-08 V with 1 pF, which is why it can hold a PMOS gate
at −3.3 V rather than merely leaking it down.

The control chain also bounds how fast that gate can be moved. `gate33`'s own 10–90 % time is what
scales with the device's gate charge: 2.0 ns at 1 pF and 9.0–9.9 ns at 5 pF, both measured with the
same level shifter. **An output device adds its gate to this node**, so its `Cgg` is not a free
parameter — it must be measured on the chain, and a several-pF gate is already inside the envelope the
5 pF case exercised (2.04 mA `vdd33` peak, 9.0 ns edge). No first-order `tox` arithmetic is quoted here
because the readable files were not used to extract an oxide capacitance.

## 3 Route A — final `VSCAN` in the same 3.3 V domain as the control high level

```
        VSCAN (= 3.3 V rail)
             │  S ┐
             │    │  M_H : p33 high-side, single device
   gate33 ───┼────┤  G        on  at VGS = −3.3 V, off at VGS = 0 V
             │  D ┘
             └──── scan electrode (column line + its pixels)
        B (p-well) ── tied to the highest potential present, i.e. to S / VSCAN
```

* **Connection / polarity**: `D` → scan electrode, `G` → `gate33`, `S` and `B` → `VSCAN`. Low gate
  selects, high gate blocks. No added keeper, no cross pull-up, no change to any accepted cell.
* **Off state**: the electrode is left **high impedance**. No bleed/discharge device is added here —
  that would be a topology decision, not a wiring detail. What is honest to say instead: a floating
  column line holds whatever charge the previously-selected row circuitry left on it, the discharge
  path then runs backwards through the pixel LEDs and the data driver, and whether that matters is a
  question about the **real electrode RC and the panel's off-state spec**, both undefined (§6).
  Residual charge must be *measured* in a later round, not assumed away by a pull-down.
* **Sizing method** (procedure, not numbers): pick `L` at the 3.3 V family's legal minimum length
  (lmin 300–350 nm from the readable rules), then sweep `W` and `m` until the measured
  `Ron(VGS = −3.3 V, VSD = VSCAN − V_data_node)` meets the §5 conditional target at the actual
  electrode current, and re-measure the same device **attached to `gate33`** so its `Cgg` is inside the
  chain's measured edge budget. Every one of those steps runs on the existing generator → full
  preflight → strict reader route with the same whole-window rule; none of them is a reason to invent a
  schematic dimension. **No illustrative `W` is written down as a final size.**
* **What this route still needs**: `Vf` (or an I–V) to know whether `3.3 V − I·Ron − margin` can
  actually be delivered to the pixel, and the leakage spec — the old draft's `≤ 0.1 µA/路` figure has
  never been verified against a 3.3 V-domain off device at any temperature.
* **Device-realizability caution carried from this project's data-driver audit**: the well/body
  connection of a 3.3 V device in this PDK is a layer-derived, die-wide question that had to be
  resolved by measurement before a body could be called isolated. **The `p33` / n-well case for a
  high-side switch has not been audited at all**, so `B`-to-`VSCAN` above is an intention to be
  verified against the LVS rules, not an established fact.

## 4 Route B — a final `VSCAN` of 5 V is a different problem, and is **not selected**

Two hard facts, both already in evidence:

1. **The control chain cannot produce the gate voltage a 5 V high-side switch needs.** `gate33` is
   measured to **3.3 V maximum**. With the device's source at 5 V, the off-state gate-source becomes
   `VGS = 3.3 − 5 = −1.7 V` — the switch is asked to block with only 1.7 V of gate overdrive removed,
   which no document in this repository defines as an off state for a device intended to hold 5 V.
2. **The released package contains no verified 5 V device family** (`n50`/`p50` model definition count
   = 0), and no absolute-rating table exists to check a stress claim against.

So the open directions for a reviewer/user to decide, **none of them chosen or simulated in this
round**:

* obtain a legitimate 5 V device option for the fixed process (teacher/foundry); or
* lower `VLED`/`VSCAN` into a domain the verified families cover — needs `Vf` first; or
* a **stacked** 3.3 V solution with independent node-by-node bias and stress verification — explicitly
  recorded as *not automatically safe*: a stack adds balancing, dynamic gate routing and a per-device
  voltage-withstand question that has no source in the readable files, and this project has measured
  how easily a nominal 3.3 V structure ends up with 3.3 V across a single gate (`DATA-2`); or
* add a boost level-shifted rail for the gate, which is a new block, a new supply domain and a new
  failure mode — outside this round's declared scope.

## 5 Current, conduction resistance and voltage margin — all conditional

```
I_SCAN   = N_active × 15 µA                       15 µA is ONE selected emitting pixel, not a line total
N_active = 768   (architecture assumption)  ->    I_SCAN = 11.52 mA   ← conditional, direction and count unconfirmed
Ron_target = V_drop_allowed / I_SCAN
           = 0.10 V / 11.52 mA ≈ 8.68 Ω           only if the old draft's 0.10 V budget is adopted
VSCAN   ≥ Vf + I_SCAN·Ron + V_data_margin        Vf: NOT DEFINED   V_data_margin: draft says ≥ 0.5 V
```

Three statements this must not be allowed to become: "the course requires 5 V", "Ron ≤ 8.68 Ω is a
specification", "11.52 mA is a measured line current". Each input is a draft condition or an
architecture assumption, and the project has already caught itself once on exactly this kind of
promotion (`DATA-1.5`'s label over-claim, and the 15.36 mA direction error in `spec` §1).

`I_SCAN` also has **never been sourced by anything simulated in this project**. The largest `vdd33`
current in the R3 record is **2.042 mA**, and that is the internal level shifter plus a declared test
capacitor — not an electrode. Sizing an output device against a load current that has no measured
counterpart yet is the reason this round stops at a plan.

## 6 Load model: the 1 pF / 5 pF are not the electrode

| node | load used so far | what it is |
|---|---|---|
| `gate33` (R2E, R3) | **1 pF / 5 pF, declared capacitor** | a **testbench load** chosen to exercise the level shifter's drive and edge behaviour. Useful only for comparing one chain against another |
| scan electrode (S3) | **NOT DEFINED** | a physical column line: metal RC, via stack, 768 pixel diodes' junction and pad capacitance, and the off-state residue of 1023 other drivers. No figure exists in any readable file |

The two must stay in separate rows of every later design table. Reusing "5 pF" as an electrode model
would be an invented number, and the R3 edge figures (2.0 ns / 9.0–9.9 ns) are therefore **chain
figures, not scan-rise figures**.

## 7 Pending parameters — the items that actually gate S3

| # | parameter | who can supply it | what it decides |
|---|---|---|---|
| P1 | **final `VSCAN` / `VLED`** (3.3 V domain, or 5 V, or something else) | teacher / user | chooses between Route A (single p33, no boost) and Route B (device option, stack, or boost). Every voltage stress number downstream depends on it, and it is the item `SOA: NO` prevents from being inferred |
| P2 | **LED `Vf`, or a usable I–V at ~15 µA** (and its temperature dependence) | device / panel data, not in the repo | the voltage actually available after `I·Ron` and the data-node margin. With `Vf` unknown, `VSCAN ≥ Vf + drop + margin` cannot be evaluated for **any** rail — this is why no route is declared feasible today |
| P3 | **scan direction and `N_active`** (how many pixels of one column emit simultaneously; is "one column, up to 768" the intended worst case) | user / architecture | `I_SCAN` (11.52 mA is conditional), hence `Ron_target`, the device `W·m`, and the data driver's peak per channel |
| P4 | **allowed on-drop and data-absorption margin** (adopt the draft's 0.10 V / 0.5 V, or set new ones) | teacher / user | `Ron_target` ≈ 8.68 Ω only under the draft pair; a different pair moves the size several-fold |
| P5 | **real electrode RC / load**, or an explicit course-simulation load figure | teacher, or a documented extraction assumption | the scan rise time and the gate charge the `gate33` node must move; without it the 1 pF / 5 pF test loads stay a stand-in and no edge budget exists |
| P6 | **off-state requirement**: leakage limit and whether a discharged/hi-Z column line is acceptable | teacher / user | whether a bleed or pull-down device belongs in the design at all, and which leakage figure it is judged against |
| P7 | **absolute ratings / SOA table** for the chosen family | foundry / teacher release | turns the measured `VGS`/`VDS` extremes into a pass/fail statement. Until it exists, `SOA: NO` and no stress claim may be closed |
| P8 | **`p33` well/body realizability** for a high-side source tied to `VSCAN` | PDK rules + measurement (this project's own audit route) | whether Route A's `B`-to-`VSCAN` is implementable, and whether a DNW variant is required |

P1, P2 and P3 are the blocking set; P4–P8 can be resolved alongside the first S3 deck.

## 8 What this plan is explicitly not

* not a sized output device, not a schematic, not a netlist for the power stage;
* not an S3 simulation, not a 5 V deck, not the 37-deck power-fail matrix, not POR/UVLO — none of these
  were run, and the round that would run them needs P1–P3 first;
* not a full-array or multi-channel claim (`S4_CHAIN: NOT_STARTED`);
* not a signoff: one corner (`tt`), one temperature (`27 °C`, a `POC_ASSUMPTION`), no mismatch, no
  Monte Carlo, no extraction;
* not a generic tool round — the R3 native waveform work used the accepted tools unchanged, and this
  plan adds no tool.

**Stopped at the R3 review gate with a decision left to the user/reviewer: the output stage's voltage
domain (P1) and the LED voltage (P2), and only then `S3`.**
