// DATA-7A single-channel dual-mode grey-scale timing controller, logic only.
//
// Observable behaviour is fixed by reports/dd1_d7a_contract.md; internal structure is this
// implementation's own choice. This module is a digital model of a future on-chip controller. It
// contains no MOS, no PAM current ladder, no LUT and no optical claim of any kind.
`timescale 1ns / 1ps

module dd1_d7a_gray_ctrl (
    input  wire        clk,          // 100 MHz reference domain used for this digital POC
    input  wire        reset_n,      // logic reset of this module only, active low
    input  wire        system_en,    // display enable: gates arming, and a mode change needs it low
    input  wire        tick,         // same-domain clock-enable, asserted ahead of the edge that
                                     // consumes it. This module never derives a clock from it.
    input  wire [1:0]  mode,         // 0 Pure 8-bit PWM, 1 Hybrid 3-bit PAM select + 6-bit time
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
    output wire [5:0]  proto_err     // sticky refusal bitmap, cleared by an accepted LATCH
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

    // proto_err bitmap
    localparam [5:0] E_LATCH     = 6'b000001, // LATCH refused: unsafe phase or window running
                   E_INCOMPLETE = 6'b000010, // cfg_valid low for the presented mode
                   E_ILLEGAL    = 6'b000100, // mode code is neither Pure nor Hybrid
                   E_MODE_RUN   = 6'b001000, // mode changed outside the safe phase
                   E_START      = 6'b010000, // PWM_START refused
                   E_AMBIGUOUS  = 6'b100000; // LATCH and a new config on the same sampling edge

    logic [2:0] state_q;
    logic [8:0] index_q;                    // interval boundaries consumed, saturating
    logic [8:0] target_q;                   // conducting intervals the displayed code asks for
    logic [2:0] disp_mode_q;
    logic [7:0] disp_pure_q;
    logic [5:0] disp_ht_q;
    logic       have_disp_q;                // a display configuration has been accepted
    logic       run_q;                      // internal conduction request before the safety gate
    logic [2:0] pam_q;
    logic [7:0] version_q;
    logic       latch_prev_q;
    logic       start_prev_q;
    logic       cfgv_prev_q;
    logic [1:0] mode_prev_q;
    logic       err_latch_q, err_incomplete_q, err_illegal_q, err_mode_run_q, err_start_q,
                err_ambiguous_q;

    // ---------------------------------------------------------------- derived request values
    wire [8:0] pure_iv  = (cfg_pure == 8'd255)     ? FULL_PURE : {1'b0, cfg_pure};
    wire [8:0] hyb_iv   = (cfg_hyb_time == 6'd63)  ? FULL_HYB  : {3'b000, cfg_hyb_time};
    wire [8:0] target_w = (mode == M_HYB)          ? hyb_iv    : pure_iv;
    wire [8:0] full_w   = (disp_mode_q == M_HYB)   ? FULL_HYB  : FULL_PURE;

    wire mode_legal    = (mode == M_PURE) || (mode == M_HYB);
    wire window_active = (state_q == S_ARMED) || (state_q == S_RUN);
    wire disp_safe     = (state_q == S_IDLE) || (state_q == S_DONE) || (state_q == S_ABORT);
    wire async_block   = blank | fault | ~reset_n;

    wire latched = latch_stb & ~latch_prev_q;
    wire started = pwm_start & ~start_prev_q;
    wire mode_change = (mode != mode_prev_q);
    wire cfg_is_new  = cfg_valid & ~cfgv_prev_q;
    // a LATCH that arrives on the same sampling edge as the configuration it points at has no
    // defined version, so it is refused and recorded rather than used
    wire ambiguous = latched & cfg_is_new;

    wire latch_ok = latched & disp_safe & blank & ~fault & reset_n & system_en
                  & mode_legal & cfg_valid & ~ambiguous;
    wire mode_change_ok = mode_change & disp_safe & blank & ~system_en;
    wire start_ok = started & disp_safe & blank & ~fault & reset_n & system_en
                  & have_disp_q & mode_legal;
    // any LATCH request that is refused leaves the display copy untouched and records a reason
    wire reject_latch     = latched & ~latch_ok;
    wire reject_start     = started & ~start_ok;
    wire reject_mode_run  = mode_change & ~mode_change_ok;

    wire tick_accept = tick & window_active & ~async_block;

    // blank is asserted by definition while the window is being armed, so only a fault may abort
    // the armed state; blank aborts a window that is already running
    wire abort_now = reset_n & (fault | (blank & (state_q == S_RUN)));

    // ---------------------------------------------------------------- refusal bitmap
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            err_latch_q     <= 1'b0;
            err_incomplete_q <= 1'b0;
            err_illegal_q   <= 1'b0;
            err_mode_run_q  <= 1'b0;
            err_start_q     <= 1'b0;
            err_ambiguous_q <= 1'b0;
        end else if (latch_ok) begin
            err_latch_q     <= 1'b0;
            err_incomplete_q <= 1'b0;
            err_illegal_q   <= 1'b0;
            err_mode_run_q  <= 1'b0;
            err_start_q     <= 1'b0;
            err_ambiguous_q <= 1'b0;
        end else begin
            if (reject_latch)                          err_latch_q     <= 1'b1;
            if (latched & ~mode_legal)                 err_illegal_q   <= 1'b1;
            if (latched & mode_legal & ~cfg_valid)      err_incomplete_q <= 1'b1;
            if (ambiguous)                             err_ambiguous_q <= 1'b1;
            if (reject_mode_run)                       err_mode_run_q  <= 1'b1;
            if (reject_start)                          err_start_q     <= 1'b1;
        end
    end

    // ---------------------------------------------------------------- state and counter
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state_q      <= S_IDLE;
            index_q      <= 9'd0;
            target_q     <= 9'd0;
            run_q        <= 1'b0;
            disp_mode_q  <= M_PURE;
            disp_pure_q  <= 8'd0;
            disp_ht_q    <= 6'd0;
            have_disp_q  <= 1'b0;
            pam_q        <= 3'd0;
            version_q    <= 8'd0;
            latch_prev_q <= 1'b0;
            start_prev_q <= 1'b0;
            cfgv_prev_q  <= 1'b0;
            mode_prev_q  <= M_PURE;
        end else begin
            latch_prev_q <= latch_stb;
            start_prev_q <= pwm_start;
            cfgv_prev_q  <= cfg_valid;
            mode_prev_q  <= mode;

            // a mode change accepted in the safe phase invalidates the prepared display, so a
            // reload / LATCH / start sequence is required before anything can light again
            if (mode_change & mode_change_ok) begin
                disp_mode_q <= mode;
                have_disp_q <= 1'b0;
                run_q       <= 1'b0;
                index_q     <= 9'd0;
                state_q     <= S_IDLE;
            end

            // accepted LATCH: all displayed fields move together
            if (latch_ok) begin
                disp_mode_q <= mode;
                disp_pure_q <= cfg_pure;
                disp_ht_q   <= cfg_hyb_time;
                target_q    <= target_w;
                pam_q       <= (mode == M_HYB) ? cfg_hyb_pam : PAM_TOP_SYMBOL;
                have_disp_q <= 1'b1;
                version_q   <= version_q + 8'd1;
            end

            // one rising PWM_START event arms the window; holding it high re-arms nothing because
            // this branch keys on the request edge, not on its level
            if (start_ok) begin
                index_q <= 9'd0;
                run_q   <= 1'b0;
                state_q <= S_ARMED;
            end

            // blank or fault during a window aborts it; withdrawing them does not resume it
            if (abort_now) begin
                state_q <= S_ABORT;
                run_q   <= 1'b0;
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
    assign data_en   = run_q & ~blank & ~fault & reset_n;
    assign data_en_b = ~data_en;
    assign obs_tick  = tick_accept;
    assign pam_sel   = pam_q;
    assign win_state = state_q;
    assign cfg_version = version_q;
    assign proto_err = {err_ambiguous_q, err_start_q, err_mode_run_q, err_illegal_q,
                        err_incomplete_q, err_latch_q};

endmodule
