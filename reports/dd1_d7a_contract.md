# DATA-7A digital contract — dual-mode grey-scale timing controller (logic only)

Baseline `731767519d1a51287eb5b7f4a6e4f9b8e613e990` (`poc/data-unit-1ch`), work branch
`poc/data-gray-d7a`. This file is written **before** the RTL, and every number and endpoint a reviewer
may check comes from here; the RTL may be restructured freely as long as the observable behaviour below
holds. Nothing in this file is a MOS, PAM-current, optical or sign-off claim: the completion level of
the whole round is `RTL_LOGIC_VERIFIED` at best.

## 0. Scope and source layering

| item | value used here | nature |
|---|---|---|
| array / refresh need | 1024 col x 768 row, 5x5 µm LED, 60–100 Hz, 15 µA is the peak target **while a pixel is selected and on** | `COURSE_REQUIREMENT` (registered statement / user definition), not a frame average |
| grey-scale schemes | Pure 8-bit PWM; Hybrid 3-bit PAM select + 6-bit PWM time | `POC_ASSUMPTION` — 2026-10-19 homework-submission spec ch. 6/9, user asked to continue it; not a line-by-line course requirement |
| event spacing | Pure 30 ns @100 Hz, 50 ns @60 Hz over 256 intervals; Hybrid 120 ns @100 Hz, 200 ns @60 Hz over 64 intervals | `POC_ASSUMPTION` + `ENGINEERING_DERIVATION` |
| emission window | 7.680 µs @100 Hz and 12.800 µs @60 Hz in **both** modes | `ENGINEERING_DERIVATION` (256×30 = 64×120, 256×50 = 64×200) |
| PAM current levels | eight select codes exist; the actual I_PAM0…I_PAM7 values, trimming and final reference relationship | `NOT DEFINED`. The values 1.875/3.75/…/15 µA are **not** adopted as official level values in this round |
| 8-bit effective optical grey, LED I-V, array RC, final VLED/VSCAN, SOA | — | `NOT_DEFINED` / `NOT_VERIFIED`; RTL proves none of it |
| reference clock inside the RTL | 100 MHz, 10 ns period | `POC_ASSUMPTION` digital condition, not a max-frequency result |

Also `NOT_IMPLEMENTED` by design in this round, and not to be inferred from anything here: the TCON
976/977 reference-cycle column schedule, the 50 MHz DCLK-to-PWM clock-domain crossing, 384-byte
shifting, SPI, frame memory, LUT, address decode, and any physical skew ≤5 ns or operating-frequency
claim. Hybrid configurations come from test vectors, not from a finished 8-bit video grey mapping.

## 1. Module boundary

One synthesizable controller `dd1_d7a_gray_ctrl` describing one data channel's future on-chip timing.
The verification harness instantiates **two** of them (`u_a`, `u_b`) behind the **same** control and
timing events, to check that two data channels start and end together and that their data stays
independent.

| direction | port | width | meaning |
|---|---|---|---|
| in | `clk` | 1 | 100 MHz reference domain |
| in | `reset_n` | 1 | active-low logic reset **of this module only** (a logic port; it is not the old C²MOS DFF having a reset, and not a real POR) |
| in | `system_en` | 1 | permitted to gate arming/start |
| in | `mode` | 2 | `2'b00` Pure, `2'b01` Hybrid; anything else is illegal |
| in | `cfg_pure` | 8 | Pure 8-bit grey code (load/next copy) |
| in | `cfg_hyb_time` | 6 | Hybrid PWM time code (load/next copy) |
| in | `cfg_hyb_pam` | 3 | Hybrid PAM select code (load/next copy) |
| in | `cfg_valid` | 1 | a complete, usable new configuration is present on the load copies |
| in | `latch_stb` | 1 | LATCH request (pulse) |
| in | `pwm_start` | 1 | PWM_START request (arm + single rising event) |
| in | `blank` | 1 | blanking request, active high |
| in | `fault` | 1 | fault, active high |
| out | `data_en` | 1 | grey-coded **and** safety-gated enable logic request |
| out | `data_en_b` | 1 | exactly `NOT data_en`, including blank/fault states — deliberately **not** the old DFF's `qbar` |
| out | `pam_sel` | 3 | the amplitude-select request held for the whole window |
| out | `win_state` | 3 | `IDLE / ARMED / RUNNING / DONE / ABORT`, observable |
| out | `cfg_version` | 8 | increments on every accepted LATCH (auditable config identity) |
| out | `proto_err` | 8 | refusal bitmap, see section 5.1; one accepted LATCH clears it, a refused request never clears anything |
| out | `obs_tick` | 1 | pulses at the ticks the controller actually accepts inside the running window; an audit node for tick consumption, never a ruler the checker measures with |

`proto_err` grew from 6 to 8 bits in the review revision, because the review required a *separate*
observable refusal reason for "LATCH with no new load" and for "LATCH asks for a mode that was never
adopted"; folding those into `LATCH_REJECTED` would have made the two failures indistinguishable in
the trace.

Configuration interface is an **abstract parallel single-channel load**, and the encoding choice is
explicit: the three fields are separate buses plus `cfg_valid` (not a packed union). For Pure, a valid
load needs `cfg_pure` and ignores the Hybrid fields; for Hybrid, it needs `cfg_hyb_time` and
`cfg_hyb_pam`. Mixing them is never an error in the wires, but `cfg_valid` asserts the mode-relevant
fields are presented; `mode` selects which ones count.

## 2. Code → conducting-interval mapping (normative)

| mode | input time code | conducting intervals | intervals in full window |
|---|---|---:|---:|
| Pure | 0 | 0 | 256 |
| Pure | 1 … 254 | equals the code | 256 |
| Pure | 255 | **256** | 256 |
| Hybrid | 0, any PAM code | 0 | 64 |
| Hybrid | 1 … 62 | equals the code | 64 |
| Hybrid | 63 | **64** | 64 |

The full window must be produced by an explicit end condition; it may **not** come from an 8-bit or
6-bit counter rolling over. After the window closes the output stays off until the next legal start.

`pam_sel` after a legal LATCH holds constant through the whole emission window **and** through the
PWM-off tail, and only changes at the next legal LATCH — it must never fall back to 0 at PWM off.
In Pure mode `pam_sel` is the highest-qualifying-level **symbol code 7**, which is a code value only:
it is not a claim that 15 µA exists anywhere.

## 3. Start, tick and time endpoints

* `pwm_start` is accepted once inside the preparation sequence where `blank=1`, `reset_n=0` has been
  released, `fault=0`, the config is valid **and authorised** (section 5), `win_state` is
  `IDLE`/`DONE`/`ABORT` and `system_en` permits it. Accepting clears the interval counter and moves to
  `ARMED`. It may be held for 40 ns; **holding it high must not re-clear on every tick.** `pwm_start`
  opens no current and consumes no interval 0.
* `t0` = the first valid tick after `blank` is released. Interval *k* is `[t0+k·T, t0+(k+1)·T)`; for
  M conducting intervals the output turns on at `t0` and off at `t0+M·T`; M=0 never turns on.
* Window end is `t0+256·T` (Pure) / `t0+64·T` (Hybrid). Expressed on one tick stream that is **257 /
  65 boundary events** (start + N interval boundaries); 256/64 is the interval count, not the count of
  boundary events including the start edge. A separate `window_end` event is equivalent and is what
  this implementation uses.
* A tick while `blank=1`, or before an accepted `pwm_start`, consumes no interval. Ticks after the
  window end must not re-open or overflow-wrap the counter.

| case | tick spacing | 100 MHz reference cycles | emission window |
|---|---:|---:|---:|
| Pure, 100 Hz example | 30 ns | 3 | 7680 ns |
| Pure, 60 Hz example | 50 ns | 5 | 12800 ns |
| Hybrid, 100 Hz example | 120 ns | 12 | 7680 ns |
| Hybrid, 60 Hz example | 200 ns | 20 | 12800 ns |

## 4. Reset, blanking, fault, abort

* After power-up/reset, outputs are off and nothing may display without a valid configuration.
* `blank`, `reset_n` and `fault` have **output-off priority**: asserted between clock edges, the final
  enable must be pulled low by combinational gating (`data_en = grey_and_state_en & ~blank & ~fault
  & reset_n`), not at the next tick. Zero-delay in simulation only proves logical priority, not MOS
  propagation delay, metastability, safe reset release or real-device glitches.
* This digital POC drives valid `blank`/`fault` pulses at least two reference cycles long at arbitrary
  phase, and `reset_n` at least 1 µs. Shorter async pulses still gate the output combinationally;
  whether the internal abort state captures them is **not** a claim of this round
  (`POC_ASSUMPTION`, not a chip input specification and not a CDC design).
* A `blank` or `fault` assertion during a running window aborts it and records an abort. Withdrawing
  only `blank`, or only clearing `fault`, must **not** resume the old window: recovery requires a new
  valid load / LATCH / start sequence in the safe phase.
* Abort/armed state is written with a single driver per register (one `always_ff` per state
  variable), so no signal is driven from two processes.

## 5. Configuration freshness, authorisation and mode adoption

Two copies exist: load/next and display. Loading a next grey code during a running window is allowed
and must not change the running waveform; the displayed code, mode and PAM select stay frozen until
the next accepted LATCH.

* A **load is a transaction, not a level.** `cfg_valid` rising (0 to 1) with the mode-relevant fields
  present arms one `load_pending` token. An accepted LATCH consumes it. Holding `cfg_valid` high,
  leaving the bus unchanged and pulsing LATCH again is a replay of a consumed load: it must be refused
  with `STALE_CONFIG` and must not step `cfg_version`. Re-presenting the same grey code is legal only
  through a new load transaction.
* A **LATCH is accepted** only while `blank=1`, no window is running or armed, reset released,
  `fault=0`, `system_en=1`, `mode` legal, `cfg_valid` high, an unconsumed load exists, and the
  presented mode equals the already-accepted mode. It then updates every displayed field atomically,
  authorises the display, consumes the load token and steps `cfg_version` by exactly one.
* `win_state` encodings are `3'd0 IDLE, 3'd1 ARMED, 3'd2 RUNNING, 3'd3 DONE, 3'd4 ABORT`.
* **Arming needs an authorised display.** `pwm_start` is accepted once, in the same safe preparation
  phase as a LATCH (`blank=1`, no window running or armed, `fault=0`, `system_en=1`, reset released),
  and only if the current display is authorised; a start presented after blank has already been
  released is refused, so a test that wants to prove an authorisation refusal must present the start
  first and release blank afterwards. Holding it high re-arms nothing. Because a LATCH and a
  start arriving on the same sampling edge would order the two by process accident, the LATCH wins and
  the start is refused with `START_REJECTED`: a start is always a later event.
* **A mode is adopted only in the safe phase**: `system_en=0`, `blank=1`, no window running or armed.
  A change of `mode` sampled at any other time is refused with `MODE_WHILE_RUNNING` and the accepted
  mode stays as it is; a LATCH can never adopt a mode (`MODE_NOT_ADOPTED`), and neither a refused LATCH
  nor a refused mode change clears a recorded error. Adoption invalidates the previous display
  authorisation and the pending load, so the new mode needs its own load and LATCH. When a mode change
  and a LATCH arrive on the same edge, adoption (if legal) happens first and the LATCH is refused.
* **An abort withdraws the authorisation and the pending load.** After a `blank` or `fault` abort,
  releasing the condition, issuing a bare `pwm_start`, loading a new code without latching it, or
  latching without a new load, must each leave the output dark; only a complete new load / LATCH /
  start sequence displays again. A load that was presented *before* the abort and never consumed is
  revoked by it as well: the same transaction cannot be committed afterwards, because the aborted
  window never took it, so recovery needs a `cfg_valid` edge that arrives after the abort.
  Priority is explicit: an abort sampled on a reference edge outranks the load, mode adoption, LATCH
  and start requests evaluated on that same edge, and none of them may re-authorise the display.
  The held `pam_sel` value is not cleared by an abort, because contract section 2 requires it to hold
  until the next legal LATCH.
* **The next copy is committed after the running window ends.** A load presented while a window is
  conducting must not change that window's code, PAM, width or mode; the first accepted LATCH after
  the window's own completion commits it, and the following window then conducts exactly the committed
  code and PAM. That load is consumed by that one LATCH: a further LATCH behind it is refused.
* Refused, with an explicit recorded reason and never silently reusing an old code: LATCH with nothing
  new, LATCH outside the safe phase or while a window runs or is armed, LATCH and the new load on the
  same reference edge, an illegal `mode`, an incomplete configuration for the presented mode, a LATCH
  presenting a mode that was not adopted, and a start with no authorised display.
* Illegal `mode`, refused LATCH and a mid-window mode change must never produce a moment of light.

### 5.1 Refusal bitmap

| bit | name | set when |
|---|---|---|
| 0 | `LATCH_REJECTED` | a LATCH request is sampled outside the safe preparation phase |
| 1 | `INCOMPLETE_CFG` | a LATCH request arrives with `cfg_valid` low for the presented mode |
| 2 | `ILLEGAL_MODE` | the presented `mode` is neither Pure nor Hybrid |
| 3 | `MODE_WHILE_RUNNING` | `mode` changes outside the safe phase, or is adopted while a window runs |
| 4 | `START_REJECTED` | a `pwm_start` edge arrives with no authorised display, or on the same edge as a LATCH |
| 5 | `LATCH_AMBIGUOUS` | `latch_stb` and a newly raised `cfg_valid` arrive on the same sampling edge |
| 6 | `STALE_CONFIG` | a LATCH request arrives with no unconsumed load to commit |
| 7 | `MODE_NOT_ADOPTED` | a LATCH presents a mode other than the accepted one |

## 6. Interface limit against the existing Data-6 cell

This round outputs a grey-scale request and a safety-gated logic enable/level code only. No old netlist
internal node is connected, forced or bypassed. `dd1_data_top_1ch` has only `d/clk/blank`, so feeding a
PWM request into `d` would still be sampled by the DFF and is **not** treated as direct control;
whether a future grey-scale top reuses the frozen analogue core or needs an explicitly timed latch
interface is a later, separately reviewed MOS decision. No port change, no bypass of the DFF, no forcing
`data_en`, no ideal source on an internal node.

## 7. How the checker is allowed to measure (fixed before the RTL)

* The checker reads the simulator's own four-state VCD for `data_en`, `data_en_b`, `pam_sel`, `mode`,
  the code buses, `cfg_valid`, `latch_stb`, `pwm_start`, `blank`, `fault`, `obs_tick`, `win_state`,
  `cfg_version`, `proto_err` and the TB's case marker; it never takes the testbench's own verdict.
* The expected interval count is recomputed from the **code value read out of the trace's input signals**
  and the **tick spacing measured from the testbench's own `tick` stimulus net** in the same trace;
  multiplying a code by a compile-time tick constant is not an observation and is not allowed as the
  golden answer. `obs_tick` is a DUT output, so it is never a measurement source: the checker only
  requires every `obs_tick` rise to coincide with a stimulus tick edge inside the running window, which
  is what makes it an audit of tick consumption rather than a ruler.
* `win_state` encoding is fixed here so the checker and the RTL mean the same thing:
  `3'd0 IDLE, 3'd1 ARMED, 3'd2 RUNNING, 3'd3 DONE, 3'd4 ABORT`. A legal main case must show `ARMED` at
  the blank release, `RUNNING` at `t0`, `DONE` at the window end, and must never reach `ABORT`.
* The reference period used to prove "the tick is a clock-enable inside one domain, not an independent
  derived clock" is measured from `clk` **inside the judged window only**; the tick spacing must be an
  integer multiple of it. Idle time between cases is not judged.
* Widths use the VCD time unit (the TB declares `1ns/1ps`, so every event timestamp is an integer ns).
* Any X/Z on a judged signal inside a judged interval is a refusal, never converted to 0 and never
  skipped; unset initial state may not leak into a window claimed valid; duplicate or non-monotonic
  timestamps, a missing signal, an empty row set and a non-finite derived number all fail.
* A conducting segment is a maximal run of `data_en=1`; every non-zero main case must show exactly one,
  with measured width equal to M·T within the trace resolution, and the output must stay off for at
  least two further ticks after the window end.
* Both instances are measured per case and their full traces compared; the mixed-code test (different
  codes per instance, common window edges) is reported apart and is not counted inside the 1536 cases.
