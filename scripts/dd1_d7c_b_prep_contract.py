#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_contract.py -- the one structured source of this round's electrical contract.

DATA-7C-B-PREP section 4. Everything the decks, the schedule and the measurement code need is written
down here once and emitted to `tests/dd1_d7c_b_prep/contract.json`; the reports and decks render from
that file, so a number cannot exist twice with two values. The status is `PROPOSED_FOR_REVIEW`: these
are the task book's POC suggestions, and an executor may not move one after seeing a result. Where the
delivered R2 bytes disagree with themselves, the suggestion stays as given and the difference is
recorded in `differences_vs_R2` for the reviewer to decide -- nothing here edits R2.

Offline only. No simulator is imported or started, no model card is read, and every electrical result
in this round remains NOT_RUN. The numbers that are labelled SYNTHETIC in the companion scripts are
hand-written arithmetic used to test the measurement code, not measurements of anything.

    python scripts/dd1_d7c_b_prep_contract.py --emit
    python scripts/dd1_d7c_b_prep_contract.py --check
"""

from __future__ import absolute_import, division, print_function

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7c_a_r2_plan as R2PLAN             # noqa: E402  (the delivered relative schedule)

CONTRACT_PATH = 'tests/dd1_d7c_b_prep/contract.json'
TASK_ID = 'DATA-7C-B-PREP'
BASE_R2 = '3e4703f1763223024f442c0826e95055782bca13'
# the reviewed PREP tip this R1 round is based on, and the review that sent it back
BASE_PREP = 'dcef9b336f2222d6291d266858270f7448b6bb78'
REVIEW_ID = 'MicroLED_DATA7C_B_PREP_Independent_Review_20261024'
CONTRACT_STATE = 'PROPOSED_FOR_REVIEW'

# ---- units, with the hand arithmetic written next to the value ---------------------------------
#
# 1 TON in the delivered plan is 1000 ns, so a nominal 120 ns platform is 0.12 TON and 200 ns is
# 0.20 TON. The unit conversions below are the ones a reviewer can check with a pencil:
#   1.875 uA = 1.875e-6 A = 1.875e9 fA
#   QLSB(120 ns) = 1.875e-6 A x 120e-9 s = 225.0e-21 C = 2.25e-13 C = 225 fC = 0.225 pC
#   QLSB(200 ns) = 1.875e-6 A x 200e-9 s = 375.0e-21 C = 3.75e-13 C = 375 fC = 0.375 pC
UNIT_CURRENT_NOMINAL_A = 1.875e-6
REFERENCE_CURRENT_A = 15e-6
BRANCHES = 8
TON_NS = float(R2PLAN.TON_NS)
LEAD_OFF_NS = 1000.0            # the pure-off preparation ends here, and the enable stays low
# R1 (the independent review of the PREP bytes) fixed the edge model: the PREP deck put a `(lead, 0)`
# point inside the first ramp, so its interpolated 50 % crossing was 1025 ns while the table declared
# 1000 ns. The repair below is the one the review allows: a named half-edge width, a uniform offset,
# and no extra point inside a ramp.
EDGE_NS = 50.0                  # Emax, the largest half-edge any transient may use
CODE_EDGE_NS = 2.0              # total width of a code-change edge: old value at t-1, new at t+1
TRANSIENT_OFFSET_NS = LEAD_OFF_NS + EDGE_NS     # 1050 ns, the same shift for every transient instant
LOGIC_HIGH_V = 1.8              # the 1.8 V logic domain; a bit is a logical value, not a volt

HAND_ARITHMETIC = [
    'Iunit_nominal = 15e-6 A x (2.5/2)/(20/2) = 15e-6 x 0.125 = 1.875e-6 A',
    '1.875 uA = 1.875e-6 A = 1.875e9 fA (multiply by 1e15 to go from A to fA)',
    'I111 nominal = 8 x 1.875e-6 A = 1.5e-5 A = 15.000 uA, which is the shared reference itself',
    'QLSB_nominal(120 ns) = 1.875e-6 A x 120e-9 s = 2.25e-13 C = 225 fC = 0.225 pC',
    'QLSB_nominal(200 ns) = 1.875e-6 A x 200e-9 s = 3.75e-13 C = 375 fC = 0.375 pC',
    'full scale band = 15 uA +/- 5% = 14.25 uA .. 15.75 uA = 1.425e-5 A .. 1.575e-5 A',
    'unit deviation limit = 0.25 x Iunit_ref; with Iunit_ref = I111/8 = 15 uA / 8 = 1.875 uA that is '
    '0.46875 uA',
    'settle band = +/- 5% of the target of the code under test, hold at least 10 ns',
    'shutoff leakage = max(abs(I_sink)) over the last 100 ns of each declared tail window <= 0.15 uA',
    '1 TON = 1000 ns, so the nominal 120 ns and 200 ns platforms are 0.12 and 0.20 TON',
]

NOMINAL_A_BY_CODE = {}
for _index, _code in enumerate(R2PLAN.DC_CODES):
    NOMINAL_A_BY_CODE[_code] = (_index + 1) * UNIT_CURRENT_NOMINAL_A

# ---- the proposed acceptance rules ---------------------------------------------------------------
RULES = {
    'process_corner': {'corner': 'TT', 'temperature_C': 27,
                       'model_family': 'SMIC18 models already used by the accepted POC',
                       'model_identity_status': 'NOT_VERIFIED_THIS_ROUND',
                       'deck_must_state_temperature': 'simopt options temp=27',
                       'note': 'no model card was opened this round; the exact local model identity is '
                               'a check for the approved native stage. The declared 27 C is only a '
                               'condition once every deck writes it as a statement: `simopt options '
                               'temp=27` is the instantiation form the accepted DATA-7B bench uses, '
                               'and a contract line is not a deck condition'},
    'enable_edges': {'half_edge_max_ns': EDGE_NS, 'symmetric_about_50_percent': True,
                     'uniform_transient_offset_ns': TRANSIENT_OFFSET_NS,
                     'pure_off_prep_end_ns': LEAD_OFF_NS,
                     'code_change_edge_total_ns': CODE_EDGE_NS,
                     'code_change_must_sit_in': 'pure_off_window',
                     'pwl_forbids_a_point_inside_a_ramp': True,
                     'note': 'the first DATA_EN ramp of TR-LONG runs 1000 ns -> 1100 ns with its 50 % '
                             'point at 1050 ns; writing a (1000, 0) hold point and then ramping to '
                             '(1050, high) would put the crossing at 1025 ns while the table says '
                             '1000 ns, which is the defect this rule exists to refuse'},
    'window_kinds': {
        'emission': {'bounds': 'rise50 -> fall50',
                     'use': 'the charge of the whole enable window, the number convergence compares'},
        'emission_flat': {'bounds': 'rise_end -> fall_start', 'use': 'the flat-part mean current'},
        'off_tail': {'bounds': 'this fall50 -> next rise_start, or the declared stop for the '
                               'last platform',
                     'use': 'signed tail Q, never folded into the emission charge'},
        'pure_off': {'bounds': 'fall_end -> next rise_start',
                    'use': 'the only region a code change or a leakage measurement may live in'},
        'leak_last100': {'bounds': 'the last 100 ns of off_tail',
                         'use': 'the magnitude test max(abs(I_sink)) against the shutoff limit, and '
                                'nothing else',
                         'must_lie_inside': 'pure_off',
                         'if_shorter': 'REFUSE_THE_CONFIGURATION, never truncate silently'}},
    'window_kind_naming': {
        'why_these_names': 'the emission and off_tail kinds keep the two words the independent review '
                           'instrument selects on, and schedule.csv keeps off_window_ns as the '
                           'pair-spelled copy of pure_off_start_ns/pure_off_stop_ns, so the reviewer '
                           'can read the repaired bytes with its own unchanged tool; the five windows '
                           'are still named apart, and both dd1_d7c_b_prep_schedule.validate and '
                           'dd1_d7c_b_prep_r1_deck_read refuse the day the pair spelling and the two '
                           'columns disagree',
        'separately_named_count': 5},
    'supplies': {'vdd18_V': 1.8, 'vcas_V': 1.8, 'iref_A': REFERENCE_CURRENT_A, 'vss_V': 0.0,
                 'vss_explicit_source': True,
                 'note': 'AGENTS.md pit 19: a vss that is not tied to a real 0 V source makes every '
                         'NMOS path disappear and the board reads as if only PMOS worked'},
    'clamp': {'main_eval_V': 1.2, 'sweep_start_V': 0.60, 'sweep_stop_V': 1.50, 'sweep_step_V': 0.05,
              'main_point_must_be_on_grid': True,
              'status': 'POC_CLAMP_CONDITION_NOT_LED_NOT_VLED_NOT_SOA'},
    'full_scale_absolute': {'code': '111', 'clamp_V': 1.2, 'target_A': 15e-6, 'tolerance_fraction': 0.05,
                            'lower_A': 14.25e-6, 'upper_A': 15.75e-6,
                            'identity': 'PROPOSED_FEASIBILITY_TARGET_NOT_SPEC'},
    'eight_level_ratio': {'iunit_ref_definition': 'Iunit_ref = I111 / 8 from the SAME DC conditions',
                          'per_code_statistic': 'Ik - (k+1) * Iunit_ref for every code',
                          'abs_deviation_limit_in_units_of_iunit_ref': 0.25,
                          'strict_monotonic_required': True,
                          'normalisation_rule': 'a scaled-down array must not be rescued by '
                                                'normalisation: the eight-level ratio pass does not '
                                                'substitute the 15 uA absolute pass'},
    'shutoff_leakage': {'tail_last_ns': 100.0, 'statistic': 'max(abs(I_sink)) over the last 100 ns',
                        'limit_A': 0.15e-6, 'signs_reported': 'both',
                        'cancellation_rule': 'a tail whose positive and negative parts nearly cancel '
                                             'is NOT zero leakage; report Q, Qpos and the magnitude of '
                                             'Qneg separately'},
    'time_step_pairing': {'nominal_maxstep_ns': R2PLAN.MAXSTEP_WIDE_NS,
                          'refined_maxstep_ns': R2PLAN.MAXSTEP_FINE_NS,
                          'only_difference_allowed': 'maxstep',
                          'identity_fields': [field for field, _ in R2PLAN.PAIR_IDENTITY_FIELDS]},
    'deck_syntax': {
        'analysis_instance_name_required': True,
        'temperature': 'simopt options temp=27',
        'dc_form': 'dc_case dc dev=Vclamp param=dc start=0.6 stop=1.5 step=0.05',
        'tran_form': 'tran_case tran stop=<this case absolute ns> maxstep=<this case ns>',
        'pwl_form': 'Vname (node 0) vsource type=pwl wave=[t1 v1 t2 v2 ...]',
        'pwl_time_suffix': 'n, whole nanoseconds',
        'proven_by': ['spectre/current_probe_syntax.scs:35', 'scripts/dd1_d7b_run.py:239',
                      'scripts/dd1_d7b_run.py:288'],
        'status': 'TEXT_CONSISTENCY_WITH_PROVEN_PROJECT_FORM_ONLY',
        'note': 'these are the spellings this project has already run on the build; adopting them is '
                'not a native syntax verdict. NATIVE_NETLIST_SYNTAX stays NOT_VERIFIED until an '
                'authorised launch reads the deck.'},
    'convergence': {'relative_measure': 'abs(dQ) / QLSB', 'limit': 0.01,
                    'also_report': 'absolute dQ in coulombs (and fC), per window',
                    'status_word_alone_is_not_a_pass': True,
                    'required_context_fields': ['sign_rule', 'threshold_V', 'window_start_ps',
                                               'window_stop_ps', 'reference_current_A'],
                    'missing_context_is_a_refusal_not_a_match': True,
                    'note': 'CONVERGED without an absolute difference is refused as an answer, and two '
                            'sides that both lack every context field are not "equal" -- they are '
                            'missing context, which is REFUSED_MISSING_CONTEXT'},
    'charge_error': {'lsb_definition': 'QLSB = Iunit_nominal x Ttick, Ttick declared per case',
                     'nominal_ticks_s': [120e-9, 200e-9],
                     'reported': ['Q_window', 'Qexpected_nominal = Inominal(k) x T50',
                                  'Qexpected_dc = IDC(k) x T50 or NOT_RUN'],
                     'proposed_limit_in_LSB': 0.5,
                     'limit_status': 'PROPOSED_NOT_CLAIMED',
                     'idc_substitution_forbidden': 'a geometry-ratio estimate is never used as IDC(k)'},
    'settling': {'band_fraction': 0.05, 'reference': 'the target current of the code under test',
                 'hold_ns': 10.0, 'deadline': 'the end of the declared window',
                 'edge_detection': 'adjacent samples plus linear interpolation at 50% of the enable '
                                   'level; no real edge is a named refusal, never a fallback to the '
                                   'window end',
                 'statuses': ['SETTLED_HELD', 'NOT_SETTLED_WITHIN_PULSE',
                              'LEFT_BAND_BEFORE_DEADLINE', 'NO_REAL_EDGE_FOUND',
                              'NOT_RUN']},
    'sampling': {'grid_forcing': 'forbidden: adaptive native samples are not snapped to a ps grid',
                 'finite_check': 'every time and current must be finite; NaN or infinity is a named '
                                 'refusal',
                 'monotonic_time': 'strictly increasing; equal or regressed time is a named refusal'},
    'launch_budget': {'total_proposed': 36, 'dut_runs': 15, 'preflight_runs': 15,
                      'syntax_debug_margin': 6, 'authorised_this_round': 0,
                      'counts': 'every launch counts, including -h, failures, aborts, crashes and '
                                'debug; REQUESTED occupies the budget before the run and recovery '
                                'never refunds it; preflight and DUT are counted separately',
                      'status': 'DRAFT_PROPOSAL_NOT_AUTHORISATION'},
}

DIFFERENCES_VS_R2 = [
    {'id': 'D1_clamp_sweep_step',
     'where_r2_says_otherwise': [
         'tests/dd1_d7c_a/native_case_plan.csv column segments: "clamp sweep 0.6 V to 1.5 V in 0.05 V '
         'steps"',
         'spectre/dd1_d7c_a_tb_draft.scs:149: "// dc_case_NNNN   dc dev=Vclamp param=dc start=0.6 '
         'stop=1.5 step=0.1"'],
     'conflict': 'the delivered table and the delivered draft deck state different sweep steps for the '
                 'same sweep, and the 0.1 V form also gives a different grid',
     'this_round_value': '0.05 V, with 1.20 V required to be an actual sweep point',
     'why': 'the task book section 4 fixes 0.60-1.50 V at 0.05 V; 0.05 V is the finer of the two, so '
            'the 1.20 V point stays on the grid either way and no R2 claim becomes false',
     'status': 'AWAITING_REVIEWER_DECISION'},
    {'id': 'D2_ton_unit_is_four_microseconds_in_the_deck',
     'where_r2_says_otherwise': [
         'spectre/dd1_d7c_a_tb_draft.scs:63 "parameters TON=4u // emission window length used by the '
         'long-pulse case (POC condition)"',
         'scripts/dd1_d7c_a_r2_plan.py:33 TON_NS = 1000 and the plan columns are written in TON'],
     'conflict': 'the deck parameter TON is 4 us while the schedule source uses TON as 1000 ns, so the '
                 'same symbol means two times that differ by a factor of four',
     'this_round_value': 'every generated deck states absolute times in ns and never uses a bare TON; '
                         'the deck keeps TON=4u only as an inherited comment, not as a timing symbol',
     'why': 'a deck whose "1.0 TON" means 4 us and a table whose "1.0 TON" means 1 us cannot be '
            'reviewed as the same stimulus',
     'status': 'AWAITING_REVIEWER_DECISION'},
    {'id': 'D3_short_pulse_note_versus_platform',
     'where_r2_says_otherwise': [
         'scripts/dd1_d7c_a_r2_plan.py:69 SHORT_CASES note "two pulses per 120 ns slot at the Hybrid '
         '100 Hz pitch"',
         'tests/dd1_d7c_a/native_case_plan.csv columns platform_TON=0.12 / 0.20 for TR-120 / TR-200'],
     'conflict': 'the prose describes two pulses inside a 120 ns slot while the machine columns '
                 'describe one 120 ns platform, and the 100 Hz pitch of a frame is not 120 ns at all',
     'this_round_value': 'one platform per emission, 120 ns for TR-120 and 200 ns for TR-200, each '
                         'stated as two absolute instants (t_rise_50, t_fall_50) plus the integration '
                         'window inside it; the frame pitch is recorded separately as a 10 ms '
                         'condition that the deck does not simulate',
     'why': 'section 5 requires that "120 ns platform" stop meaning two different pairs of instants',
     'status': 'AWAITING_REVIEWER_DECISION'},
    {'id': 'D4_tr_long_starts_conducting_at_t_zero',
     'where_r2_says_otherwise': [
         'tests/dd1_d7c_a/native_case_plan.csv TR-LONG stimulus_start_TON=0 and segments '
         '"000@0-1"',
         'reports/dd1_d7c_a_native_test_plan.md: "TR-LONG 在一个 deck 内排八个长发光窗"'],
     'conflict': 'the first platform begins at t=0 with the enable already high, so there is no rising '
                 'edge to detect for the first window and an edge finder would have to invent one',
     'this_round_value': 'a uniform 1 us initial-off lead is inserted (LEAD_OFF_NS=1000), every '
                         'platform, code change, integration window and stop shifts by the same amount, '
                         'and the offset is recorded per case in the schedule table',
     'why': 'section 5 asks for exactly this: the initial code settles before the first enable, and a '
            'level already high at t=0 is not a rising edge',
     'status': 'RESOLVED_BY_THIS_ROUND_WITHIN_THE_ALLOWED_SHIFT'},
    {'id': 'D5_integration_window_is_narrower_than_the_platform',
     'where_r2_says_otherwise': [
         'tests/dd1_d7c_a/native_case_plan.csv TR-120 window_TON=0.13-0.23 while platform_TON=0.12 '
         'starting at 0.12'],
     'conflict': 'the declared window is 100 ns inside a 120 ns platform, which is right (the platform '
                 'is inset by the 10 ns edges) but the prose calls both of them "the 120 ns window"',
     'this_round_value': 'platform start/stop, 50% enable edges, and the integration window are separate '
                         'named columns everywhere: platform_start_ns, platform_stop_ns, '
                         'enable_rise_50_ns, enable_fall_50_ns, full_window_start_ns, '
                         'full_window_stop_ns, flat_start_ns, flat_stop_ns',
     'why': 'the charge of a window is only comparable between a nominal and a refined run if the '
            'window is one pair of instants, not a length in prose',
     'status': 'RESOLVED_BY_THIS_ROUND_WITHIN_THE_ALLOWED_SHIFT'},
    {'id': 'D6_transient_offset_is_1050_ns_not_1000_ns',
     'where_r2_says_otherwise': [
         'tests/dd1_d7c_a/native_case_plan.csv TR-LONG stimulus_start_TON=0, platform_TON=1.0, '
         'edge_TON=0.05 (all relative)',
         'tests/dd1_d7c_b_prep/schedule.csv as delivered at the PREP tip: lead_off_ns=1000.000 with '
         'the first enable ramp written 950 -> 1050 and declared at 1000.000'],
     'conflict': 'R2 declares only relative times, so the absolute shift is this round\'s own choice, '
                 'and the PREP bytes chose one number for the table (1000 ns) and another for the '
                 'waveform it actually generated (1025 ns interpolated)',
     'this_round_value': 'every transient instant is R2 relative time + 1050 ns; the pure-off '
                         'preparation ends at 1000 ns, the first ramp is 1000 -> 1100 ns and its 50 % '
                         'point is 1050 ns, which is the number the table and the deck now share',
     'why': 'a window whose declared edge and generated edge differ by 25 ns is not the window the '
            'integration was planned on, and the reviewer read this off the delivered PWL',
     'status': 'CORRECTED_BY_R1_WITHIN_THE_ALLOWED_SHIFT_NOT_A_CHANGE_TO_R2'},
]

# The independent review of the PREP bytes (2026-10-24, tip dcef9b3) named four families. They are
# recorded here rather than only in prose, because the schedule, the decks and the measurement entry
# all have to change together and one source has to say what "fixed" means.
REPAIRS_R1 = [
    {'id': 'F1_PAM_bit_order_and_high_level',
     'defect': 'the three-character code string was written left-to-right into pam0/pam1/pam2, so '
               'pam0 received the weight-4 bit, and the high level was 1.0 V instead of the 1.8 V '
               'logic domain; four DC codes (001, 011, 100, 110) carried another code\'s identity',
     'repair': 'value = int(code, 2); bit(k) = (value >> k) & 1; volts = bit * logic_high_V, used by '
               'the DC decks and the transient PWL alike, and read back from the delivered decks by '
               'an independent parser rather than from the generator',
     'reviewer_fact': 'REVIEW_DATA7C_B_PREP_20261024.md section 3 F1, checks/prep_probe.json '
                      'F1.dc_code_mismatches (4 rows) and F1.nonrail_highs (12 rows)'},
    {'id': 'F2_PWL_and_window_physics',
     'defect': 'each PAM bit was written as one point per change with no hold pair, so PWL '
               'interpolation ramped the bit straight through the emission windows (36 overlaps); the '
               'first enable ramp carried an extra (lead, 0) point (declared 1000 ns, real crossing '
               '1025/1010 ns); 20 declared off windows ran backwards; 20 leakage windows contained the '
               'next DATA_EN rise up to 0.9 V',
     'repair': 'a code change is old value at t-1 and new value at t+1 inside the pure-off window; '
               'windows are five named kinds (see rules.window_kinds) with start strictly less than '
               'stop; the leakage window must lie wholly inside the pure-off window or the '
               'configuration is refused; the 50 % edges are interpolated from the delivered PWL and '
               'must equal the table',
     'reviewer_fact': 'REVIEW_DATA7C_B_PREP_20261024.md section 3 F2, checks/prep_probe.json '
                      'F2.PAM_ramps_over_emission_count=36, backwards_off_windows=20, '
                      'leakage_windows_with_next_enable=20, enable_50_percent_errors'},
    {'id': 'F3_measurement_entry_wiring',
     'defect': 'measure_case() handed the flat window bounds to the edge finder as the edge hint with '
               'a +/-5 ns search, so all eight TR-LONG windows answered NO_REAL_EDGE_FOUND; it took '
               'the first off_tail for every window and broke, so a 5 uA fault in a later tail was '
               'missed; it never called sign_check or charge_errors, and convergence accepted two '
               'sides with no context at all',
     'repair': 'each emission window searches around its own rise50/fall50, reports the full-enable '
               'Q and the flat mean separately, keeps Qpos / signed Qneg / |Qneg|, calls sign_check '
               'and charge_errors, pairs window k with tail k, and refuses instead of falling back',
     'reviewer_fact': 'REVIEW_DATA7C_B_PREP_20261024.md section 3 F3, checks/prep_probe.json '
                      'F3.entries (eight NO_REAL_EDGE_FOUND), F3.second_tail_independent_reference '
                      '(ABOVE_LIMIT 5e-06 A while the main entry reported 0.0 A), '
                      'F3.missing_pair_context_still_accepted=true'},
    {'id': 'F4_native_deck_known_contract',
     'defect': 'fifteen decks wrote bare `dc dev=...` / `tran stop=...` analysis lines and no '
               '`simopt options temp=27`, while this project has already run named analysis instances '
               'and an explicit temperature; the PWL spelling also differed from the proven '
               '`type=pwl wave=[...]` form',
     'repair': 'decks state simopt options temp=27, an instance-named analysis line, and PWL as '
               'wave=[t v ...] with whole-nanosecond n-suffixed times; the audit parses the effective '
               'statement instead of matching a substring, so a comment can no longer vouch for a deck',
     'reviewer_fact': 'REVIEW_DATA7C_B_PREP_20261024.md section 3 F4, checks/prep_probe.json '
                      'F4.no_explicit_27C (all 15) and F4.unnamed_analysis_lines (all 15); the review '
                      'states plainly that this is textual inconsistency with proven project syntax, '
                      'not a reproduced native error'},
]

FROZEN_CANDIDATE_DUT = [
    'spectre/dd1_d7c_a_gates.scs', 'spectre/dd1_d7c_a_pam_dec.scs',
    'spectre/dd1_d7c_a_sink_unit.scs', 'spectre/dd1_d7c_a_pam_top.scs']

NOT_VERIFIED = ['NATIVE_NETLIST_SYNTAX', 'HIERARCHICAL_SAVE_SYNTAX', 'PWL_SPELLING_ON_DECODER_INPUTS',
                'MODEL_CARD_IDENTITY', 'GEOMETRY_LEGALITY_AGAINST_PDK']
NOT_RUN = ['PAM_8LEVEL_CURRENT_MEASURED', 'PWM_PAM_CURRENT_INTEGRATION',
           'FULL_MOS_GRAY_CONTROLLER', 'GRAY_LUT', 'SHUTOFF_LEAKAGE_MEASURED',
           'CONVERGENCE_PAIR_MEASURED', 'DC_OPERATING_POINTS']


def sweep_points():
    """the clamp sweep as an explicit list, so 1.20 V is a point and not a claim"""
    value = RULES['clamp']['sweep_start_V']
    points = []
    while value <= RULES['clamp']['sweep_stop_V'] + 1e-12:
        points.append(round(value, 10))
        value += RULES['clamp']['sweep_step_V']
    return points


def contract():
    points = sweep_points()
    data = {
        'schema_version': '1.0',
        'task_id': TASK_ID,
        'round': 'R1',
        'repair_task_id': 'DATA-7C-B-PREP-R1',
        'contract_state': CONTRACT_STATE,
        'user_approved': 'NO',
        'reviewer_frozen': 'NO',
        'base_r2_sha': BASE_R2,
        'base_prep_sha': BASE_PREP,
        'branch': 'poc/data-pam-d7c-b-prep-r1',
        'repository': 'https://github.com/LINboss666/microled-ic-ai-lab',
        'single_source': 'scripts/dd1_d7c_b_prep_contract.py emits this file; decks, schedule and '
                         'reports render from it and from nothing else',
        'units': {'ton_ns': TON_NS, 'lead_off_ns': LEAD_OFF_NS, 'edge_ns': EDGE_NS,
                  'transient_offset_ns': TRANSIENT_OFFSET_NS, 'code_edge_ns': CODE_EDGE_NS,
                  'logic_high_V': LOGIC_HIGH_V,
                  'current': 'ampere', 'time': 'second', 'charge': 'coulomb',
                  'display_precision_rule': 'a ns column with four decimals resolves at 0.1 ps, and '
                                            'every tolerance names its LSB and its quantisation term'},
        'hand_arithmetic': HAND_ARITHMETIC,
        'nominal_current_A_by_code': dict((code, NOMINAL_A_BY_CODE[code])
                                          for code in R2PLAN.DC_CODES),
        'nominal_current_identity': 'ESTIMATED_MIRROR_RATIO_ONLY',
        'device_geometry': {'mref_w_l_um': [20.0, 2.0], 'unit_mcas_mout_w_l_um': [2.5, 2.0],
                            'mpass_mbleed': 'NOT_RESIZED_THIS_ROUND',
                            'count_source': 'parsed from the delivered netlists by '
                                            'scripts/netlist_stats.py, never retyped'},
        'conduction': {'data_en_high': 'conducting branches = pam_sel + 1',
                       'data_en_low': 'all eight branches off',
                       'code_000_status': 'LOWEST NON-ZERO LEVEL, not a black code',
                       'black_code_substitution': 'forbidden'},
        'clamp_sweep_points_V': points,
        'rules': RULES,
        'probe': {'instance': R2PLAN.PROBE_INST, 'terminals': list(R2PLAN.PROBE_TERMINALS),
                  'definition': 'I_sink = Ip_branch',
                  'physical_positive_path': ['clamp_node', 'data_out', 'the conducting branch', 'vss'],
                  'sign_rule': R2PLAN.SIGN_CONVENTION,
                  'abs_forbidden_on': ['raw current', 'total charge'],
                  'tail_sign': 'a shutoff tail may be positive or negative; it is never pre-assumed '
                               'to be a negative area'},
        'schedule': {'source_relative_to': 'scripts/dd1_d7c_a_r2_plan.py',
                     'lead_off_ns': LEAD_OFF_NS, 'edge_ns': EDGE_NS,
                     'offset_applied_to_every_transient_ns': TRANSIENT_OFFSET_NS,
                     'shift_rule': 'platform, 50% edges, ramp endpoints, code change, integration '
                                   'window, tail, pure-off, leakage sub-window and stop all shift by '
                                   'the same 1050 ns; the pure-off preparation ends at 1000 ns and the '
                                   'first ramp starts there, so no hold point sits inside a ramp',
                     'pam_bit_rule': 'value = int(code, 2); pam0 = bit 0 (weight 1), pam1 = bit 1 '
                                     '(weight 2), pam2 = bit 2 (weight 4); level = bit x 1.8 V',
                     'window_kinds': sorted(RULES['window_kinds'])},
        'repairs_r1': REPAIRS_R1,
        'launch_budget': RULES['launch_budget'],
        'frozen_candidate_dut': FROZEN_CANDIDATE_DUT,
        'differences_vs_R2': DIFFERENCES_VS_R2,
        'not_verified': NOT_VERIFIED,
        'not_run': NOT_RUN,
        'results_column_state': 'NOT_RUN for all fifteen cases; a synthetic number never enters an '
                                'electrical result'}
    return data


def selfcheck(data):
    """arithmetic over the emitted contract; every refusal names the rule it broke"""
    problems = []
    points = data['clamp_sweep_points_V']
    clamp = data['rules']['clamp']
    if points[0] != clamp['sweep_start_V'] or points[-1] != clamp['sweep_stop_V']:
        problems.append('the sweep grid does not start at %s or end at %s: %s..%s'
                        % (clamp['sweep_start_V'], clamp['sweep_stop_V'], points[0], points[-1]))
    if len(points) != len(set(points)):
        problems.append('the sweep grid repeats a point')
    if clamp['main_eval_V'] not in points:
        problems.append('the main evaluation clamp %s V is not a point of the %d-step sweep'
                        % (clamp['main_eval_V'], clamp['sweep_step_V']))
    expected_count = int(round((clamp['sweep_stop_V'] - clamp['sweep_start_V'])
                               / clamp['sweep_step_V'])) + 1
    if len(points) != expected_count:
        problems.append('the sweep has %d points, the declared range and step need %d'
                        % (len(points), expected_count))
    nominal = data['nominal_current_A_by_code']
    if len(nominal) != 8:
        problems.append('the nominal table carries %d codes, the candidate has eight' % len(nominal))
    values = [nominal[code] for code in R2PLAN.DC_CODES]
    if any(values[i] >= values[i + 1] for i in range(len(values) - 1)):
        problems.append('the nominal ladder is not strictly increasing')
    for code, value in nominal.items():
        weight = int(code, 2) + 1
        if abs(value - weight * UNIT_CURRENT_NOMINAL_A) > 1e-18:
            problems.append('code %s claims %r A, the geometry ratio gives %r A'
                            % (code, value, weight * UNIT_CURRENT_NOMINAL_A))
    full = data['rules']['full_scale_absolute']
    if abs(full['target_A'] - nominal['111']) > 1e-18:
        problems.append('the full-scale target %r is not eight unit currents %r'
                        % (full['target_A'], nominal['111']))
    if abs(full['upper_A'] - full['target_A'] * 1.05) > 1e-18 or \
            abs(full['lower_A'] - full['target_A'] * 0.95) > 1e-18:
        problems.append('the 5% band is not the declared target times 0.95 and 1.05')
    for tick, expected in ((120e-9, 2.25e-13), (200e-9, 3.75e-13)):
        computed = UNIT_CURRENT_NOMINAL_A * tick
        if abs(computed - expected) > 1e-24:
            problems.append('QLSB at %g s computes %r, the hand arithmetic says %r'
                            % (tick, computed, expected))
    if abs(UNIT_CURRENT_NOMINAL_A * 1e15 - 1.875e9) > 1e-6:
        problems.append('1.875 uA is not 1.875e9 fA, so the unit column is wrong')
    pair = data['rules']['time_step_pairing']
    if pair['nominal_maxstep_ns'] <= pair['refined_maxstep_ns']:
        problems.append('the refined step %s ns is not finer than the nominal %s ns'
                        % (pair['refined_maxstep_ns'], pair['nominal_maxstep_ns']))
    if data['contract_state'] != CONTRACT_STATE:
        problems.append('the contract state left PROPOSED_FOR_REVIEW')
    if data['launch_budget']['dut_runs'] + data['launch_budget']['preflight_runs'] + \
            data['launch_budget']['syntax_debug_margin'] != data['launch_budget']['total_proposed']:
        problems.append('the launch parts do not add up to the proposed total')
    if data['launch_budget']['authorised_this_round'] != 0:
        problems.append('this round authorises no launch, the budget field says otherwise')
    if not data['differences_vs_R2']:
        problems.append('a round that found no difference in the delivered bytes should say why it '
                        'looked')
    # ---- the R1 timing model, checked as arithmetic rather than trusted as prose -----------------
    units = data['units']
    edges = data['rules']['enable_edges']
    if units['transient_offset_ns'] != units['lead_off_ns'] + units['edge_ns']:
        problems.append('the transient offset %s ns is not the pure-off end %s ns plus the half-edge '
                        '%s ns, which is the only way the first ramp can start where preparation ends'
                        % (units['transient_offset_ns'], units['lead_off_ns'], units['edge_ns']))
    if abs(units['logic_high_V'] - data['rules']['supplies']['vdd18_V']) > 1e-12:
        problems.append('the logic high used by the PAM sources (%s V) is not the declared 1.8 V logic '
                        'domain, so a bit is being turned into volts by some other rule'
                        % units['logic_high_V'])
    if units['edge_ns'] != edges['half_edge_max_ns']:
        problems.append('the edge unit and the declared half-edge maximum disagree')
    for name, ton in (('TR-LONG', R2PLAN.LONG_EDGE_TON),
                      ('TR-120/TR-200', R2PLAN.SHORT_CASES[0][3]),
                      ('TR-OFFCODE', R2PLAN.OFFCODE_CASE[3])):
        if ton * TON_NS > units['edge_ns']:
            problems.append('%s wants a %s ns half-edge, above the declared maximum %s ns'
                            % (name, ton * TON_NS, units['edge_ns']))
    if units['code_edge_ns'] >= min(R2PLAN.LONG_OFF_GAP_TON * TON_NS,
                                    R2PLAN.SHORT_CASES[0][2] * TON_NS,
                                    R2PLAN.OFFCODE_CASE[2] * TON_NS):
        problems.append('a %s ns code edge cannot fit inside the smallest off gap this round uses'
                        % units['code_edge_ns'])
    kinds = data['rules']['window_kinds']
    if sorted(kinds) != sorted(['emission', 'emission_flat', 'off_tail',
                                'pure_off', 'leak_last100']):
        problems.append('the window kinds are %s, the review asked for these five and no others'
                        % ','.join(sorted(kinds)))
    if kinds['leak_last100']['must_lie_inside'] != 'pure_off':
        problems.append('the leakage sub-window is not required to sit inside the pure-off window, '
                        'which is how a next enable can hide inside a previous tail')
    syntax = data['rules']['deck_syntax']
    declared = ' '.join(str(value) for value in syntax.values() if isinstance(value, str))
    for key, needle in (('temp', 'simopt options temp=27'), ('pwl', 'type=pwl wave='),
                        ('dc', ' dc dev=Vclamp param=dc'), ('tran', ' tran stop=')):
        if needle not in declared:
            problems.append('the deck syntax rule does not name the %s form the review cited' % key)
    if len(data['repairs_r1']) != 4:
        problems.append('the R1 repair list carries %d entries, the review named four families'
                        % len(data['repairs_r1']))
    for item in data['repairs_r1']:
        for field in ('id', 'defect', 'repair', 'reviewer_fact'):
            if not item.get(field):
                problems.append('repair %s has no %s, so it is a claim without a finding behind it'
                                % (item.get('id'), field))
    if [item['id'] for item in data['repairs_r1']] != \
            ['F1_PAM_bit_order_and_high_level', 'F2_PWL_and_window_physics',
             'F3_measurement_entry_wiring', 'F4_native_deck_known_contract']:
        problems.append('the repair list does not name the four families the review used, so a '
                        'repaired gap could be swapped for an unrelated change')
    if not any(item['id'].startswith('D6') for item in data['differences_vs_R2']):
        problems.append('the 1050 ns offset decision is not recorded as a difference against the '
                        'delivered bytes; the reviewer has to see it, not infer it')
    return problems


def emit(path=None):
    data = contract()
    problems = selfcheck(data)
    if problems:
        for line in problems:
            print('  CONTRACT_REFUSED ' + line)
        raise SystemExit('D7C_B_CONTRACT: refused to emit, %d problem(s)' % len(problems))
    target = path or os.path.join(ROOT, CONTRACT_PATH)
    if not os.path.isdir(os.path.dirname(target)):
        os.makedirs(os.path.dirname(target))
    with io.open(target, 'wb') as handle:
        handle.write((json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    return target, data


def load(path=None):
    target = path or os.path.join(ROOT, CONTRACT_PATH.replace('/', os.sep))
    return json.loads(io.open(target, encoding='utf-8').read())


CONTRACT_MARKDOWN = 'reports/dd1_d7c_b_prep_contract.md'


def render_markdown(data):
    """the contract report: rendered from the JSON only, never typed a second time"""
    add = []
    a = add.append
    a('# DATA-7C-B-PREP 电气合同草案（状态 %s，不是 USER_APPROVED）' % data['contract_state'])
    a('')
    a('机读来源：`tests/dd1_d7c_b_prep/contract.json`，由 `scripts/dd1_d7c_b_prep_contract.py` 生成；'
      '本文件由同一脚本渲染，任何一处手工改数都会让 `--check` 的固定点比较失败。')
    a('基线 R2 = `%s`，分支 `%s`。本轮不运行任何仿真器：Spectre 0 次（含 `-h`）、RTL 仿真 0 次、'
      'OA 写入 0 次、动态 preflight 0 次；15 例结果列一律 `NOT_RUN`。' % (data['base_r2_sha'],
                                                                           data['branch']))
    a('')
    a('## 1 条件与建议判据')
    a('')
    a('| 项 | 建议值 | 判读方式与限制 |')
    a('|---|---|---|')
    r = data['rules']
    a('| 工艺角与温度 | %s / %s °C | 模型身份本轮未读卡，`%s`，确切本地模型留给获批原生阶段核验 |'
      % (r['process_corner']['corner'], r['process_corner']['temperature_C'],
         r['process_corner']['model_identity_status']))
    s = r['supplies']
    a('| 供电与参考 | VDD18=%s V、VCAS=%s V、Iref=%s A 外供、VSS 显式接 0 | 参考是 bench 电流计注入'
      '二极管连接 Mref 的节点，不是理想 VBIAS；vss 不接地时所有 NMOS 通路不存在（桥手册坑 19） |'
      % (s['vdd18_V'], s['vcas_V'], s['iref_A']))
    c = r['clamp']
    a('| 主评价输出夹持 | %s V | 继承 POC 条件；不代表实际 LED、VLED 或最终 SOA（`%s`） |'
      % (c['main_eval_V'], c['status']))
    a('| 输出夹持扫描 | %s–%s V，步长 %s V | 1.20 V 必须是实际扫描点：网格 %s 点，第 %d 点即为它 |'
      % (c['sweep_start_V'], c['sweep_stop_V'], c['sweep_step_V'], len(data['clamp_sweep_points_V']),
         data['clamp_sweep_points_V'].index(c['main_eval_V']) + 1))
    f = r['full_scale_absolute']
    a('| 满堂绝对电流 | 码 111 在 %s V 为 %s A ±%s%%（%s–%s A） | 候选可行性目标，不是规格；'
      '八档相对比例通过**不能**代替这一条 |'
      % (f['clamp_V'], f['target_A'], int(f['tolerance_fraction'] * 100), f['lower_A'], f['upper_A']))
    e = r['eight_level_ratio']
    a('| 八档比例 | `Iunit_ref = I111/8`（同条件 DC 实测），逐档报 `Ik-(k+1)*Iunit_ref` | '
      '建议绝对偏差不超过 %s 个 Iunit_ref，且八码严格单调；归一基准全表一致，不得逐码换基准 |'
      % e['abs_deviation_limit_in_units_of_iunit_ref'])
    k = r['shutoff_leakage']
    a('| 关断漏流 | 每个关断尾窗末 %s ns 内 `max(abs(I_sink)) <= %s A` | 正负方向都报，不得把有'
      '正负反冲的尾段相消后写成零漏流；abs 只用于这条幅度判据，不用于总电荷 |'
      % (k['tail_last_ns'], k['limit_A']))
    m = r['time_step_pairing']
    a('| 细步长配对 | 普通 %s ns / 细化 %s ns | 完整激励历史相同，只改 maxstep；配对的 %d 个字段必须'
      '逐字相等 |' % (m['nominal_maxstep_ns'], m['refined_maxstep_ns'], len(m['identity_fields'])))
    v = r['convergence']
    a('| 收敛 | 同窗口 `abs(dQ)/QLSB <= %s` | 同时必须给出绝对差（C 与 fC）；只报 `CONVERGED` '
      '不算答案 |' % v['limit'])
    ch = r['charge_error']
    a('| 电荷误差 | 以声明的 QLSB 报两种口径：对名义、对该档实测 DC | 候选建议限 %s LSB，'
      '**只作为待审判据**，本轮不宣称已满足；无 DC 原生值时后一种为 `NOT_RUN`，不得用几何比冒充 |'
      % ch['proposed_limit_in_LSB'])
    se = r['settling']
    a('| 入带 | 目标电流 ±%s%%，持续至少 %s ns，deadline 为该窗自身末点 | 状态封闭集合 %s；'
      '曾入带但在 deadline 前离带必须报 `LEFT_BAND_BEFORE_DEADLINE` |'
      % (se['band_fraction'], se['hold_ns'], ', '.join(se['statuses'])))
    sa = r['sampling']
    a('| 样点 | %s | %s；%s |' % (sa['finite_check'], sa['grid_forcing'], sa['monotonic_time']))
    a('')
    a('## 1.1 R1 的激励时间模型（本轮按复审把这一节写进合同）')
    a('')
    u = data['units']
    a('| 量 | 值 | 为什么必须是这个值 |')
    a('|---|---|---|')
    a('| 纯关态预备结束 | %s ns | 使能在这一段全程为 0，初始码自 t=0 稳定 |' % u['lead_off_ns'])
    a('| 半沿宽 Emax | %s ns | 三个瞬态族的沿宽（TR-LONG %g、TR-120/200 %g、TR-OFFCODE %g ns）都不得'
      '超过它，否则表里的 50%% 点与 PWL 的交点不是同一个数 |'
      % (u['edge_ns'], R2PLAN.LONG_EDGE_TON * TON_NS, R2PLAN.SHORT_CASES[0][3] * TON_NS,
         R2PLAN.OFFCODE_CASE[3] * TON_NS))
    a('| 统一偏移 | %s ns | 每个瞬态时刻 = R2 相对时刻 + 这个数；首沿 50%% 因此是 %s ns，斜坡 '
      '%s→%s ns，表与波形同一个数 |'
      % (u['transient_offset_ns'], u['transient_offset_ns'], u['lead_off_ns'],
         u['lead_off_ns'] + 2 * u['edge_ns']))
    a('| 换码沿 | 总宽 %s ns（中心前 %s ns 写旧值、中心后 %s ns 写新值） | 两点都必须落在纯关态窗内；'
      '只写"上一次目标→下一次目标"会让 PWL 直线穿过发光窗，PREP 字节里正是 36 段这样的斜坡 |'
      % (u['code_edge_ns'], u['code_edge_ns'] / 2, u['code_edge_ns'] / 2))
    a('')
    a('### 1.2 五种窗，各自有名字，不再混用')
    a('')
    a('| 种类 | 边界 | 用途 |')
    a('|---|---|---|')
    for name in ('emission', 'emission_flat', 'off_tail', 'pure_off',
                 'leak_last100'):
        kind = r['window_kinds'][name]
        extra = ''
        if name == 'leak_last100':
            extra = '；必须完整位于 `%s` 内，不足 %s ns 就 `%s`' % (
                kind['must_lie_inside'], r['shutoff_leakage']['tail_last_ns'], kind['if_shorter'])
        a('| `%s` | %s | %s%s |' % (name, kind['bounds'], kind['use'], extra))
    a('')
    a('### 1.3 deck 必须写出的形式（来源是本项目已跑过的写法，不是本轮的猜测）')
    a('')
    for key in ('temperature', 'dc_form', 'tran_form', 'pwl_form', 'pwl_time_suffix'):
        a('* `%s` ← `%s`' % (key, r['deck_syntax'][key]))
    a('* 已证出处：%s。本轮没有运行仿真，所以这只是与已证文本的一致性，`NATIVE_NETLIST_SYNTAX` 仍为 '
      '`NOT_VERIFIED`，不许写成原生语法 PASS。' % ', '.join('`%s`' % p for p in
                                                             r['deck_syntax']['proven_by']))
    a('')
    a('## 1.4 R1 修补的四组（复审点名，逐组对着审核事实）')
    a('')
    for item in data['repairs_r1']:
        a('* **`%s`** — 缺陷：%s。修法：%s。审核事实：%s'
          % (item['id'], item['defect'], item['repair'], item['reviewer_fact']))
    a('')
    a('## 2 名义电流阶梯（身份全部 %s）' % data['nominal_current_identity'])
    a('')
    a('| PAM 码 | 导通支路数 | 名义电流 / µA | µA 的 SI 写法 |')
    a('|---|---:|---:|---|')
    for code in sorted(data['nominal_current_A_by_code']):
        value = data['nominal_current_A_by_code'][code]
        a('| `%s` | %d | %g | %g = %g = %g |' % (code, int(code, 2) + 1, value * 1e6, value,
                                                 value, value * 1e15))
    a('')
    a('代码位权：`pam_sel0`=bit0 权重 1，`pam_sel1`=bit1 权重 2，`pam_sel2`=bit2 权重 4；'
      '码 `000` 是**最低非零档**（一条支路），不得当黑码。')
    a('')
    a('### 2.1 手算对照')
    a('')
    for line in data['hand_arithmetic']:
        a('* `%s`' % line)
    a('')
    a('## 3 探针、符号与窗口口径')
    a('')
    p = data['probe']
    a('* 探针实例 `%s`，端序 `(%s %s)`，定义 `%s`。' % (p['instance'], p['terminals'][0],
                                                        p['terminals'][1], p['definition']))
    a('* 物理正方向：%s。' % ' -> '.join(p['physical_positive_path']))
    a('* %s' % p['sign_rule'])
    a('* 禁止取绝对值的对象：%s。' % ', '.join(p['abs_forbidden_on']))
    a('* %s' % p['tail_sign'])
    a('')
    a('## 4 日程来源与平移量')
    a('')
    a('* 相对时刻唯一来源：%s；本轮绝对时刻由 `scripts/dd1_d7c_b_prep_schedule.py` 计算并写入 '
      '`tests/dd1_d7c_b_prep/schedule.csv`。' % data['schedule']['source_relative_to'])
    a('* 统一初始关断预备 `%g ns`，`offset_applied_ns` 逐例记录；平台、换码点、积分窗、尾窗与 stop '
      '同一偏移量平移，不逐例各说各话。' % data['schedule']['lead_off_ns'])
    a('* %s' % data['schedule']['shift_rule'])
    a('')
    a('## 5 与已交付 R2 字段的差异（保留建议值，等审核定夺）')
    a('')
    a('| id | R2 另一头的说法 | 冲突 | 本轮值 | 为什么不默改 | 状态 |')
    a('|---|---|---|---|---|---|')
    for item in data['differences_vs_R2']:
        a('| `%s` | %s | %s | %s | %s | %s |'
          % (item['id'], '<br>'.join('`%s`' % s for s in item['where_r2_says_otherwise']),
             item['conflict'], item['this_round_value'], item['why'], item['status']))
    a('')
    a('## 6 启动额度草案（本轮授权仍为 0）')
    a('')
    lb = data['launch_budget']
    a('* 建议总额 %d 次：DUT %d + 供电/激励 preflight %d + 语法调试收敛余量 %d。%s'
      % (lb['total_proposed'], lb['dut_runs'], lb['preflight_runs'], lb['syntax_debug_margin'],
         lb['status']))
    a('* %s' % lb['counts'])
    a('* 每例进程数逐行列在 `schedule.csv` 的 `launch_processes_dut` / `launch_processes_preflight`'
      ' 两列（各 1），不只写"15 例"。')
    a('* 本轮不实现新的生产级账本；记账纪律沿用 DATA-7B 已接受的 `REQUESTED/UNCERTAIN/` 五态规则'
      '（`scripts/dd1_d7b_run.py` 的 `Account`），未来启动前必须先绑定：R2 接受版、本合同 SHA、'
      '执行源码 SHA、电流与电荷判据、原生总额度、本机只读环境核验范围。缺任一项都不能拿本任务书当令牌。')
    a('* DATA-7B 历史 `%s`：不借用、不重置、不抵扣、不改绿。' % '59_OF_56_OVER_BY_3 已 VIOLATED')
    a('')
    a('## 7 本轮不做、未证与待决')
    a('')
    a('* 未证：%s。' % ', '.join(data['not_verified']))
    a('* 未跑：%s。' % ', '.join(data['not_run']))
    a('* 冻结件（本轮零修改）：%s。' % ', '.join('`%s`' % p for p in data['frozen_candidate_dut']))
    a('* %s' % data['results_column_state'])
    a('')
    a('## 8 采纳路径（等审核与用户，执行者不自批）')
    a('')
    a('1. 电流归一取同条件 DC 的 `I111/8`，还是取名义单位电荷；两者结果都要能同时呈现。')
    a('2. 电荷误差限 %s LSB、偏差不超过 %s 个 Iunit_ref、漏流 %s A、收敛 %s×QLSB 是否照单采纳。'
      % (r['charge_error']['proposed_limit_in_LSB'],
         r['eight_level_ratio']['abs_deviation_limit_in_units_of_iunit_ref'],
         r['shutoff_leakage']['limit_A'], r['convergence']['limit']))
    a('3. §5 五条差异逐条裁定：接受本轮值、回到 R2 说法，还是另定第三种。')
    a('4. 原生阶段总额 %d 次是否批准，以及 preflight 与 DUT 的分列记账口径。' % lb['total_proposed'])
    a('')
    return '\n'.join(add).rstrip('\n') + '\n'


def emit_markdown(path=None, data=None):
    text = render_markdown(data or contract())
    target = path or os.path.join(ROOT, CONTRACT_MARKDOWN.replace('/', os.sep))
    if not os.path.isdir(os.path.dirname(target)):
        os.makedirs(os.path.dirname(target))
    with io.open(target, 'wb') as handle:
        handle.write(text.encode('utf-8'))
    return target


def markdown_is_current():
    """the delivered report must be exactly what the contract renders, in both directions"""
    target = os.path.join(ROOT, CONTRACT_MARKDOWN.replace('/', os.sep))
    if not os.path.isfile(target):
        return ['%s is missing' % CONTRACT_MARKDOWN]
    with io.open(target, encoding='utf-8', newline='') as handle:
        delivered = handle.read()
    rendered = render_markdown(contract())
    problems = []
    if delivered != rendered:
        problems.append('%s is not the text contract.json renders' % CONTRACT_MARKDOWN)
    if '\r' in delivered:
        problems.append('%s carries CR bytes' % CONTRACT_MARKDOWN)
    if delivered.endswith('\n\n'):
        problems.append('%s ends with a blank line at EOF' % CONTRACT_MARKDOWN)
    return problems


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--emit', action='store_true')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', default='')
    arguments = parser.parse_args(argv)
    if arguments.emit:
        target, data = emit(arguments.out or None)
        print('D7C_B_CONTRACT_EMIT %s (%d bytes, %d sweep points, %d differences recorded)'
              % (target.replace(os.sep, '/'), os.path.getsize(target),
                 len(data['clamp_sweep_points_V']), len(data['differences_vs_R2'])))
    if arguments.render:
        path = emit_markdown()
        problems = markdown_is_current()
        print('D7C_B_CONTRACT_RENDER %s (%d bytes, delivered_matches=%s)'
              % (path.replace(os.sep, '/'), os.path.getsize(path), not problems))
        for line in problems:
            print('  PROBLEM ' + line)
        if arguments.emit:
            return 0
    if arguments.check:
        delivered = load(arguments.out or None)
        problems = selfcheck(delivered)
        rebuilt = contract()
        drift = [key for key in rebuilt if json.dumps(rebuilt[key], sort_keys=True) !=
                 json.dumps(delivered.get(key), sort_keys=True)]
        problems = problems + ['source file disagrees on %s' % key for key in sorted(drift)]
        problems = problems + markdown_is_current()
        markdown_rows = len([1 for line in io.open(
            os.path.join(ROOT, CONTRACT_MARKDOWN.replace('/', os.sep)), encoding='utf-8').read()
            .split('\n') if line.startswith('| `')])
        print('D7C_B_CONTRACT_CHECK: %s (state=%s sweep_points=%d markdown_rows=%d problems=%d)'
              % ('PASS' if not problems else 'FAIL', delivered['contract_state'],
                 len(delivered['clamp_sweep_points_V']), markdown_rows, len(problems)))
        for line in problems[:12]:
            print('  PROBLEM ' + line)
        return 1 if problems else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
