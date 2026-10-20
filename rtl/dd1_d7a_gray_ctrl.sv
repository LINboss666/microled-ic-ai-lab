// DATA-7A single-channel dual-mode grey-scale timing controller, logic only.
//
// Observable behaviour is fixed by reports/dd1_d7a_contract.md. This revision closes the four
// protocol defects an independent review reproduced against the previous versions: an abort let a bare
// PWM_START re-light the old configuration, a repeated LATCH with no new load was accepted, a
// LATCH could adopt a mode outside the safe phase, and a pending load prepared *before* an abort still
// authorised a display *after* it. Still a digital model of a future on-chip controller: no MOS, no
// PAM current ladder, no LUT, no optical claim.
`timescale 1ns / 1ps

module dd1_d7a_gray_ctrl (
    input  wire        clk,          // 100 MHz reference domain used for this digital POC
    input  wire        reset_n,      // logic reset of this module only, active low
    input  wire        system_en,    // display enable: gates arming, and a mode change needs it low
    input  wire        tick,         // same-domain clock-enable, asserted ahead of the edge that
                                     // consumes it. This module never derives a clock from it.
    input  wire [1:0]  mode,         // requested mode: 0 Pure 8-bit PWM, 1 Hybrid 3+6
    input  wire [7:0]  cfg_pure,     // load / next copy
    input  wire [5:0]  cfg_hyb_time, // load / next copy
    input  wire [2:0]  cfg_hyb_pam,  // load / next copy
    input  wire        cfg_valid,    // the mode-relevant fields of the load copy are complete
    input  wire        latch_stb,    // LATCH request
    input  wire        pwm_start,    // PWM_START request, may be held
    input  wire        blank,        // blanking request, active high
    input  wire        fault,        // fault, active high
    output wire        data_en,      // grey-coded request, already safety-gated
    output wire        data_en_b,    // exactly NOT data_en
    output wire        obs_tick,     // ticks this controller actually accepted: an audit node
    output wire [2:0]  pam_sel,      // amplitude-select request held for the whole window
    output wire [2:0]  win_state,
    output wire [7:0]  cfg_version,  // one step per accepted LATCH
    output wire [7:0]  proto_err     // sticky refusal bitmap, cleared by an accepted LATCH
);

    localparam [2:0] S_IDLE  = 3'd0,
                     S_ARMED = 3'd1,
                     S_RUN   = 3'd2,
                     S_DONE  = 3'd3,
                     S_ABORT = 3'd4;
    localparam [1:0] M_PURE = 2'd0,
                     M_HYB  = 2'd1;
    localparam [8:0] FULL_PURE = 9'd256,   // intervals in a Pure window
                     FULL_HYB   = 9'd64;   // intervals in a Hybrid window
    localparam [2:0] PAM_TOP_SYMBOL = 3'd7; // a code value only, not a current level

    // proto_err bitmap: one bit per refusal reason, several may be set by one bad request
    localparam [7:0] E_LATCH      = 8'b0000_0001, // unsafe phase: running, not blanked, or disabled
                   E_INCOMPLETE  = 8'b0000_0010, // cfg_valid low for the presented mode
                   E_ILLEGAL     = 8'b0000_0100, // mode code is neither Pure nor Hybrid
                   E_MODE_RUN    = 8'b0000_1000, // mode changed outside the safe phase
                   E_START       = 8'b0001_0000, // PWM_START refused
                   E_AMBIGUOUS   = 8'b0010_0000, // LATCH and a new load on the same sampling edge
                   E_STALE       = 8'b0100_0000, // LATCH with no unconsumed new load to commit
                   E_MODE_UNSET  = 8'b1000_0000; // LATCH asks for a mode not adopted in the safe phase

    logic [2:0] state_q;
    logic [8:0] index_q;                    // interval boundaries consumed, saturating
    logic [8:0] target_q;                   // conducting intervals the displayed code asks for
    logic [1:0] disp_mode_q;                // the ONLY mode the outputs may act on
    logic [7:0] disp_pure_q;
    logic [5:0] disp_ht_q;
    logic       auth_q;                     // the displayed configuration may be armed and run
    logic       load_pending_q;             // an unconsumed complete load exists
    logic       run_q;                      // internal conduction request before the safety gate
    logic [2:0] pam_q;
    logic [7:0] version_q;
    logic       latch_prev_q, start_prev_q, cfgv_prev_q;
    logic [1:0] mode_prev_q;
    logic       err_latch_q, err_incomplete_q, err_illegal_q, err_mode_run_q, err_start_q,
                err_ambiguous_q, err_stale_q, err_mode_unset_q;

    // ---------------------------------------------------------------- derived request values
    wire [8:0] pure_iv  = (cfg_pure == 8'd255)    ? FULL_PURE : {1'b0, cfg_pure};
    wire [8:0] hyb_iv   = (cfg_hyb_time == 6'd63) ? FULL_HYB  : {3'b000, cfg_hyb_time};
    wire [8:0] target_w = (mode == M_HYB)         ? hyb_iv    : pure_iv;
    wire [8:0] full_w   = (disp_mode_q == M_HYB)  ? FULL_HYB  : FULL_PURE;

    wire mode_legal    = (mode == M_PURE) || (mode == M_HYB);
    wire window_active = (state_q == S_ARMED) || (state_q == S_RUN);
    wire disp_safe     = (state_q == S_IDLE) || (state_q == S_DONE) || (state_q == S_ABORT);
    wire async_block   = blank | fault | ~reset_n;

    wire latched    = latch_stb & ~latch_prev_q;
    wire started    = pwm_start & ~start_prev_q;
    wire mode_change = (mode != mode_prev_q);
    wire cfg_is_new  = cfg_valid & ~cfgv_prev_q;

    // a LATCH that arrives on the same sampling edge as the load it points at has no defined
    // version, so it is refused and recorded rather than used
    wire ambiguous = latched & cfg_is_new;
    // a complete load is a transaction: cfg_valid rising arms it, an accepted LATCH consumes it
    wire load_arrived = cfg_is_new & cfg_valid;

    // safe-phase mode adoption needs the display disabled, blank asserted and no window activity
    wire mode_change_ok  = mode_change & mode_legal & disp_safe & blank & ~system_en;
    wire mode_change_bad = mode_change & ~mode_change_ok;

    wire phase_ok  = disp_safe & blank & ~fault & reset_n & system_en;
    wire mode_matches_accepted = (mode == disp_mode_q);
    wire latch_ok  = latched & phase_ok & mode_legal & cfg_valid & load_pending_q
                   & mode_matches_accepted & ~ambiguous;
    wire start_ok  = started & phase_ok & auth_q & mode_legal & ~latched;

    wire tick_accept = tick & window_active & ~async_block;

    // blank is asserted by definition while the window is being armed, so only a fault may abort the
    // armed state; blank aborts a window that is already running
    wire abort_now = reset_n & (fault | (blank & (state_q == S_RUN)));

    // ---------------------------------------------------------------- refusal bitmap
    // An accepted LATCH clears only the LATCH-family record. A start refusal or an unsafe mode change
    // sampled on that very edge must survive it, otherwise a successful action would wash out the
    // evidence of a concurrent protocol violation.
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            err_latch_q      <= 1'b0;
            err_incomplete_q <= 1'b0;
            err_illegal_q    <= 1'b0;
            err_mode_run_q   <= 1'b0;
            err_start_q      <= 1'b0;
            err_ambiguous_q  <= 1'b0;
            err_stale_q      <= 1'b0;
            err_mode_unset_q <= 1'b0;
        end else if (latch_ok) begin
            err_latch_q      <= 1'b0;
            err_incomplete_q <= 1'b0;
            err_illegal_q    <= 1'b0;
            err_ambiguous_q  <= 1'b0;
            err_stale_q      <= 1'b0;
            err_mode_unset_q <= 1'b0;
            if (started & ~start_ok)                      err_start_q      <= 1'b1;
            if (mode_change_bad)                          err_mode_run_q   <= 1'b1;
        end else begin
            if (latched & ~phase_ok)                    err_latch_q      <= 1'b1;
            if (latched & mode_legal & ~cfg_valid)      err_incomplete_q <= 1'b1;
            if (latched & ~mode_legal)                  err_illegal_q    <= 1'b1;
            if (mode_change_bad)                        err_mode_run_q   <= 1'b1;
            if (started & ~start_ok)                    err_start_q      <= 1'b1;
            if (ambiguous)                              err_ambiguous_q  <= 1'b1;
            if (latched & ~load_pending_q)               err_stale_q      <= 1'b1;
            if (latched & ~mode_matches_accepted)        err_mode_unset_q <= 1'b1;
        end
    end

    // ---------------------------------------------------------------- state, config and counter
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state_q        <= S_IDLE;
            index_q        <= 9'd0;
            target_q       <= 9'd0;
            run_q          <= 1'b0;
            disp_mode_q    <= M_PURE;
            disp_pure_q    <= 8'd0;
            disp_ht_q      <= 6'd0;
            auth_q         <= 1'b0;
            load_pending_q <= 1'b0;
            pam_q          <= 3'd0;
            version_q      <= 8'd0;
            latch_prev_q   <= 1'b0;
            start_prev_q   <= 1'b0;
            cfgv_prev_q    <= 1'b0;
            mode_prev_q    <= M_PURE;
        end else begin
            latch_prev_q <= latch_stb;
            start_prev_q <= pwm_start;
            cfgv_prev_q  <= cfg_valid;
            mode_prev_q  <= mode;

            // An abort is the highest-priority sampled event. It withdraws the display
            // authorisation AND the unconsumed pending load that was prepared before it, so a LATCH
            // arriving after the abort cannot commit a configuration the aborted window never
            // consumed; load, mode adoption, LATCH and start sampled on this same edge are all
            // suppressed, and recovery needs a load, a LATCH and a start that come after the abort.
            if (abort_now) begin
                state_q        <= S_ABORT;
                run_q          <= 1'b0;
                auth_q         <= 1'b0;
                load_pending_q <= 1'b0;
            end else begin
                // one complete load becomes one consumable pending config
                if (load_arrived) begin
                    load_pending_q <= 1'b1;
                end

                // a mode adopted in the safe phase invalidates the prepared display: the old code must
                // not stay armed under the new mode, so a fresh load and LATCH are required
                if (mode_change_ok) begin
                    disp_mode_q    <= mode;
                    auth_q         <= 1'b0;
                    load_pending_q <= 1'b0;
                    run_q          <= 1'b0;
                    index_q        <= 9'd0;
                    state_q        <= S_IDLE;
                end

                // accepted LATCH: the display copies move together and the load is consumed
                if (latch_ok) begin
                    disp_pure_q    <= cfg_pure;
                    disp_ht_q      <= cfg_hyb_time;
                    target_q       <= target_w;
                    pam_q          <= (mode == M_HYB) ? cfg_hyb_pam : PAM_TOP_SYMBOL;
                    auth_q         <= 1'b1;
                    load_pending_q <= 1'b0;
                    version_q      <= version_q + 8'd1;
                end

                // one rising PWM_START event arms the window, and only for an authorised display;
                // holding it high re-arms nothing because this keys on the request edge, not the level
                if (start_ok) begin
                    index_q <= 9'd0;
                    run_q   <= 1'b0;
                    state_q <= S_ARMED;
                end
            end

            // tick consumption: interval k starts at the edge that consumes the k-th accepted tick
            if (tick_accept) begin
                if (state_q == S_ARMED) begin
                    state_q <= S_RUN;
                end
                if (index_q < full_w) begin
                    run_q   <= (index_q < target_q);
                    index_q <= index_q + 9'd1;
                end else begin
                    run_q   <= 1'b0;          // explicit window end, never a counter rollover
                    state_q <= S_DONE;
                end
            end
        end
    end

    // ---------------------------------------------------------------- outputs
    // output-off priority is combinational: blank, fault or reset pull the enable down between
    // clock edges instead of waiting for the next tick
    assign data_en     = run_q & ~blank & ~fault & reset_n;
    assign data_en_b   = ~data_en;
    assign obs_tick    = tick_accept;
    assign pam_sel     = pam_q;
    assign win_state   = state_q;
    assign cfg_version = version_q;
    assign proto_err   = {err_mode_unset_q, err_stale_q, err_ambiguous_q, err_start_q,
                          err_mode_run_q, err_illegal_q, err_incomplete_q, err_latch_q};

endmodule
