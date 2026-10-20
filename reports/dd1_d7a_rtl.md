# DATA-7A RTL implementation note — what the controller is, and what it is not

Baseline `731767519d1a51287eb5b7f4a6e4f9b8e613e990`, branch `poc/data-gray-d7a`. The normative
behaviour is `reports/dd1_d7a_contract.md`; this file only explains how this implementation meets it.
Completion level of the round is `RTL_LOGIC_VERIFIED` at best: no MOS circuit, no PAM current ladder,
no LUT, no optical grey scale, no layout.

## 1. Structure

One synthesizable module `dd1_d7a_gray_ctrl` (`rtl/dd1_d7a_gray_ctrl.sv`, 20 ports) describes one data
channel. The harness (`tests/dd1_d7a/tb_dd1_d7a_gray.sv`) instantiates two of them behind shared
`clk / tick / blank / fault / reset_n / system_en / latch_stb / pwm_start / cfg_valid / mode`, with
per-channel grey codes, so a common start and a common window end are observable rather than assumed.

Three concurrent domains of behaviour, deliberately separated:

| part | written by | purpose |
|---|---|---|
| `state_q, index_q, target_q, run_q, disp_*_q, have_disp_q, version_q, pam_q, *_prev_q, err_*_q` | one `always_ff @(posedge clk or negedge reset_n)` per group | protocol, window sequencing, display copy |
| `tick_accept`, `abort_now`, `latch_ok`, `start_ok`, refusal set | `wire` expressions | decisions sampled on the reference edge |
| `data_en`, `data_en_b`, `obs_tick`, `pam_sel`, `win_state`, `cfg_version`, `proto_err` | `assign` from one register each, or the register directly | output-off priority is combinational |

Two registers exist only because of the independent review, each with exactly one driver:

* `auth_q` — the display authorisation. Set only by an accepted LATCH; cleared by reset, by safe-phase
  mode adoption and by an abort. `start_ok` requires it, so a bare `pwm_start` after an abort cannot
  re-light the old configuration, while a window that completed normally keeps its authorisation for
  the next frame.
* `load_pending_q` — the consumable load token. Set by the rising edge of `cfg_valid`, cleared by the
  accepted LATCH that commits it, and dropped without committing by a reset or a safe-phase mode
  change. "One load feeds one LATCH" is therefore a property of the circuit, not of testbench
  discipline.

`pam_q` is written only at an accepted LATCH and is never cleared by an abort, a window end or PWM
off; `disp_mode_q` is written only by the safe-phase adoption path, never by a LATCH.

No signal is driven from two processes. There is no `initial` value, no `#delay`, no `force`, and no
hierarchy below the module, which is what the yosys pass re-checks independently (section 5).

## 2. Interval arithmetic

`index_q` counts consumed interval boundaries from 0; `full_w` is 256 for the displayed Pure mode and
64 for Hybrid. At each accepted tick:

* if `index_q < full_w`: `run_q <= (index_q < target_q)` and `index_q <= index_q + 1`;
* otherwise `run_q <= 0` and `state_q <= S_DONE`.

`index_q` therefore never rolls over: the full window is an explicit end condition, and a tick that
arrives after `S_DONE` is not accepted at all. `target_q` is snapshotted at an accepted LATCH from the
hand table `(mode, code) -> intervals` (`Pure 255 -> 256`, `Hybrid 63 -> 64`, everything else the code
itself), so loading a next code during a running window cannot move the running waveform.

`pam_q` is written only at an accepted LATCH — to `cfg_hyb_pam` in Hybrid, to the symbol value 7 in
Pure — and is never re-cleared at PWM off or at window end.

## 3. Start, tick and blank

`t0` is not a signal: it is the reference edge that consumes the first tick presented after `blank`
falls. `pwm_start` is consumed as a rising **event** (`pwm_start & ~start_prev_q`), so holding it for
40 ns — or for the whole window — cannot re-clear the counter. `tick` is a same-domain clock-enable
supplied by the test reference domain; the module never uses it as a clock, never generates a clock
from it, and does not implement its divider (that belongs to the frame/TCON logic, `NOT_IMPLEMENTED`
here).

`data_en = run_q & ~blank & ~fault & reset_n` and `data_en_b = ~data_en`. The gate is
combinational, so an assertion between clock edges removes the enable at that same simulation time.
`data_en_b` is the complement of the final enable, not the old C²MOS `qbar`.

`abort_now = reset_n & (fault | (blank & state_q == S_RUN))`: blank aborts a running window only,
because arming legitimately happens while `blank` is still asserted. An abort is the highest-priority
sampled branch: it records `S_ABORT`, clears `run_q`, withdraws `auth_q` **and** clears
`load_pending_q`, so a load that was prepared before the abort and never consumed cannot be committed
after it. Withdrawing blank or clearing fault cannot resume, because tick acceptance requires
`S_ARMED`/`S_RUN`. Recovery needs a load edge that arrives after the abort, then a LATCH, then a start.
The load, mode-adoption, LATCH and start branches are evaluated in the `else` arm of the same edge, so
none of them can act while the abort is taking the display away.

## 4. Refusals

`proto_err` is a sticky eight-bit map. An accepted LATCH clears the six LATCH-family bits; a start
refusal or an unsafe mode change sampled on that same edge survives, so a successful action cannot
erase the evidence of a concurrent protocol violation:

| bit | name | set when |
|---|---|---|
| 0 | `LATCH_REJECTED` | a LATCH request arrives outside the safe phase (window running or armed, blank released, fault, system disabled) |
| 1 | `INCOMPLETE_CFG` | a LATCH request arrives with `cfg_valid` low for the presented mode |
| 2 | `ILLEGAL_MODE` | a LATCH request arrives with a `mode` code that is neither Pure nor Hybrid |
| 3 | `MODE_WHILE_RUNNING` | `mode` changes while the display is enabled or a window is armed/running |
| 4 | `START_REJECTED` | a `pwm_start` edge arrives with no authorised display, or on the same edge as a LATCH |
| 6 | `STALE_CONFIG` | a LATCH request arrives with no unconsumed load behind it |
| 7 | `MODE_NOT_ADOPTED` | a LATCH presents a mode other than the one adopted in the safe phase |
| 5 | `LATCH_AMBIGUOUS` | `latch_stb` and a newly presented `cfg_valid` arrive on the same sampling edge |

A refused request never changes the displayed code, mode or PAM select, and never lights: LATCH is the
only path that writes the display copies, and arming is refused without a displayed configuration.

## 5. Independent structure check

`python scripts/dd1_d7a_run.py --synth --out <run>` runs yosys on the RTL alone (testbench not read,
no cell library): `read_verilog -sv`, `hierarchy -check -top`, `proc`, `opt_expr`, `opt_clean`,
`check -assert`, `flatten`, `opt -fine`, `opt_clean -purge`, `check -assert`, `stat`, and
`select -assert-none` for `$dlatch`, `$sr`, `$dffe`, `$memory`, `$anyseq`, `$anyconst`. This is a
front-end expansion and structural statement only: no technology mapping, no timing, no area.

The inferred storage is 21 async-reset flip-flop cells (6 `$adff`, 15 `$adffe`) covering the window
state, the interval index, the target count, the run flag, the display copies, the version counter,
the held PAM code, the request-edge memories (`latch_prev_q`, `start_prev_q`, `cfgv_prev_q`,
`mode_prev_q`) and the six refusal bits. Every one of them is intentional sequencer state; there is no
latch, no memory array and no storage that this note has not accounted for.

## 6. What this round does not connect

The controller output is a logic enable and a level code. Nothing is wired to the frozen Data-6
netlist: `dd1_data_top_1ch` has only `d/clk/blank`, so feeding a PWM request into `d` would still be
sampled by its DFF and is not treated as direct control. Reusing the frozen analogue core under a new
grey-scale top, or designing an explicitly timed latch interface, is a later MOS decision with its own
review. `NEW_SPECTRE_RUNS=0`, `NEW_OA_WRITES=0` for this whole round.
