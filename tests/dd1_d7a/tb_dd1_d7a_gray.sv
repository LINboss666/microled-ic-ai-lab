// DATA-7A dual-instance testbench for dd1_d7a_gray_ctrl.
//
// It replays a deterministic vector file: one line per case, whitespace-separated
//
//   id profile mode pure_a pure_b ht_a ht_b pam_a pam_b tick_div p1 p2 p3 p4
//
// `profile` selects the stimulus sequence. Every input is driven in the reference clock domain with
// an explicit setup ahead of the edge that samples it and a hold after it, and the case marker
// `case_id` moves at the start of each case, so the independent checker can segment the dump and
// measure tick spacing, window endpoints and conducting widths out of the waveforms themselves.
// The testbench never computes a verdict.
`timescale 1ns / 1ps

module tb_dd1_d7a_gray;

    localparam [2:0] S_IDLE  = 3'd0,
                     S_ARMED = 3'd1,
                     S_RUN   = 3'd2,
                     S_DONE  = 3'd3,
                     S_ABORT = 3'd4;

    localparam integer TICK_LEAD = 5;      // the enable is raised this many ns before the edge that
                                           // consumes it, so it is a clock-enable, not a clock
    localparam integer TICK_HIGH = 6;      // and stays up past that edge by TICK_HIGH - TICK_LEAD

    reg clk = 1'b0;
    reg reset_n = 1'b0;
    reg system_en = 1'b0;
    reg tick = 1'b0;
    reg blank = 1'b1;
    reg fault = 1'b0;
    reg [1:0] mode = 2'd0;
    reg [7:0] cfg_pure_a = 8'd0, cfg_pure_b = 8'd0;
    reg [5:0] cfg_ht_a = 6'd0, cfg_ht_b = 6'd0;
    reg [2:0] cfg_pam_a = 3'd0, cfg_pam_b = 3'd0;
    reg cfg_valid = 1'b0;
    reg latch_stb = 1'b0;
    reg pwm_start = 1'b0;
    reg [31:0] case_id = 32'hxxxx_xxxx;

    wire        data_en_a, data_en_ba, obs_tick_a;
    wire [2:0]  pam_sel_a, win_state_a;
    wire [7:0]  cfg_version_a;
    wire [5:0]  proto_err_a;
    wire        data_en_bb, data_en_b_b, obs_tick_b;
    wire [2:0]  pam_sel_b, win_state_b;
    wire [7:0]  cfg_version_b;
    wire [5:0]  proto_err_b;

    dd1_d7a_gray_ctrl u_a (
        .clk(clk), .reset_n(reset_n), .system_en(system_en), .tick(tick), .mode(mode),
        .cfg_pure(cfg_pure_a), .cfg_hyb_time(cfg_ht_a), .cfg_hyb_pam(cfg_pam_a),
        .cfg_valid(cfg_valid), .latch_stb(latch_stb), .pwm_start(pwm_start),
        .blank(blank), .fault(fault),
        .data_en(data_en_a), .data_en_b(data_en_ba), .obs_tick(obs_tick_a),
        .pam_sel(pam_sel_a), .win_state(win_state_a), .cfg_version(cfg_version_a),
        .proto_err(proto_err_a));

    dd1_d7a_gray_ctrl u_b (
        .clk(clk), .reset_n(reset_n), .system_en(system_en), .tick(tick), .mode(mode),
        .cfg_pure(cfg_pure_b), .cfg_hyb_time(cfg_ht_b), .cfg_hyb_pam(cfg_pam_b),
        .cfg_valid(cfg_valid), .latch_stb(latch_stb), .pwm_start(pwm_start),
        .blank(blank), .fault(fault),
        .data_en(data_en_bb), .data_en_b(data_en_b_b), .obs_tick(obs_tick_b),
        .pam_sel(pam_sel_b), .win_state(win_state_b), .cfg_version(cfg_version_b),
        .proto_err(proto_err_b));

    // ---------------------------------------------------------------- reference clock
    reg clk_stall = 1'b0;
    always begin
        while (clk_stall) begin
            #5;
        end
        #5 clk = ~clk;                      // 10 ns period, rising at 5, 15, 25 ...
    end
    // tick_run arms the enable; each asserted tick is placed TICK_LEAD ns before the reference edge
    // that consumes it, so the tick is a clock-enable inside this domain, never a derived clock.
    reg  tick_run = 1'b0;
    integer tick_div = 3;
    integer div_ctr = 0;
    integer ticks_sent = 0;

    always @(negedge clk) begin
        if (!tick_run) begin
            tick = 1'b0;
            div_ctr = 0;
        end else if (div_ctr == 0) begin
            div_ctr = tick_div - 1;             // so consecutive tick rises are tick_div periods apart
            tick = 1'b1;
            ticks_sent = ticks_sent + 1;
            #(TICK_HIGH);
            tick = 1'b0;
        end else begin
            div_ctr = div_ctr - 1;
        end
    end

    // ---------------------------------------------------------------- vector replay
    integer fd, rc, ncases;
    integer cid, prof, md, pa, pb, ha, hb, pama, pamb, tdiv, p1, p2, p3, p4;
    reg [8*256:1] vfile;
    reg [8*256:1] vcdfile;

    task automatic edges;
        input integer n;
        integer k;
        begin
            for (k = 0; k < n; k = k + 1) @(posedge clk);
        end
    endtask

    // mid-cycle drive helpers: every input change lands 2 ns after a rising edge, i.e. 8 ns of
    // setup before the next sampling edge
    task automatic drive_begin;
        begin
            @(posedge clk);
            #2;
        end
    endtask

    task automatic power_on_reset;
        begin
            blank = 1'b1;
            fault = 1'b0;
            system_en = 1'b0;
            tick_run = 1'b0;
            pwm_start = 1'b0;
            latch_stb = 1'b0;
            cfg_valid = 1'b0;
            cfg_pure_a = 8'd0; cfg_pure_b = 8'd0;
            cfg_ht_a = 6'd0;   cfg_ht_b = 6'd0;
            cfg_pam_a = 3'd0;  cfg_pam_b = 3'd0;
            reset_n = 1'b0;
            edges(120);                        // 1.2 us, above the 1 us contract minimum
            reset_n = 1'b1;
            edges(2);
        end
    endtask

    task automatic set_mode;
        input integer m;
        begin
            drive_begin;
            mode = m[1:0];
            edges(2);
        end
    endtask

    task automatic enable_system;
        begin
            drive_begin;
            system_en = 1'b1;
            edges(1);
        end
    endtask

    // present a complete load copy, then LATCH it on a later edge (never the same one)
    task automatic load_and_latch;
        input integer pure_a;
        input integer pure_b;
        input integer ht_a;
        input integer ht_b;
        input integer pam_a;
        input integer pam_b;
        begin
            drive_begin;
            cfg_pure_a = pure_a[7:0];
            cfg_ht_a   = ht_a[5:0];
            cfg_pam_a  = pam_a[2:0];
            if (pure_b == pure_a && ht_b == ht_a && pam_b == pam_a) begin
                cfg_pure_b = pure_a[7:0];
                cfg_ht_b   = ht_a[5:0];
                cfg_pam_b  = pam_a[2:0];
            end else begin
                cfg_pure_b = pure_b[7:0];
                cfg_ht_b   = ht_b[5:0];
                cfg_pam_b  = pam_b[2:0];
            end
            cfg_valid = 1'b1;
            edges(2);
            drive_begin;
            latch_stb = 1'b1;                  // high across exactly one sampling edge
            edges(2);
            drive_begin;
            latch_stb = 1'b0;
            cfg_valid = 1'b0;
            edges(1);
        end
    endtask

    // PWM_START is held for `hold_ns` and must be accepted as one rising event only
    task automatic arm_start;
        input integer hold_ns;
        integer k;
        begin
            drive_begin;
            pwm_start = 1'b1;
            k = hold_ns;
            while (k > 0) begin
                edges(1);
                k = k - 10;
            end
            #2;
            pwm_start = 1'b0;
            edges(1);
        end
    endtask

    task automatic run_window;
        input integer intervals;               // 256 or 64
        input integer div;
        begin
            tick_div = div;
            drive_begin;
            blank = 1'b0;                      // released mid-cycle, ahead of the first tick
            tick_run = 1'b1;
            edges((intervals + 9) * div);      // window end plus the idle tail
            tick_run = 1'b0;
            edges(2);
            drive_begin;
            blank = 1'b1;
            edges(2);
        end
    endtask

    task automatic run_case;
        input integer id;
        input integer profile;
        input integer m;
        input integer pure_a;
        input integer pure_b;
        input integer ht_a;
        input integer ht_b;
        input integer pam_a;
        input integer pam_b;
        input integer tdiv;
        input integer q1;
        input integer q2;
        integer intervals;
        begin
            drive_begin;
            case_id = id;                                  // segment boundary for the checker
            power_on_reset;
            set_mode(m);
            enable_system;
            intervals = (m == 1) ? 64 : 256;
            case (profile)
                0: begin                                   // legal main matrix case
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                1: begin                                   // next code loaded during a running window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges(((q1 == 0) ? (intervals / 2) : q1) * tdiv);
                    drive_begin;
                    cfg_pure_a = q2; cfg_pure_b = q2;
                    cfg_ht_a = q2[5:0]; cfg_ht_b = q2[5:0];
                    cfg_valid = 1'b1;
                    edges(2);
                    drive_begin;
                    cfg_valid = 1'b0;
                    edges((intervals + 9) * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    drive_begin;
                    blank = 1'b1;
                    edges(2);
                end
                2: begin                                   // blank asserted in the middle of a window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;                       // the tick stream never stops here
                    edges(q1 * tdiv);
                    drive_begin;
                    blank = 1'b1;                          // aborts the window
                    edges(6);
                    drive_begin;
                    blank = 1'b0;                          // withdrawn, must not resume the window
                    edges(8);
                    tick_run = 1'b0;
                    edges(2);
                    drive_begin;
                    blank = 1'b1;
                    edges(2);
                end
                3: begin                                   // fault asserted in the middle of a window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;                       // ticks keep coming through the fault
                    edges(q1 * tdiv);
                    drive_begin;
                    fault = 1'b1;
                    edges(4);
                    drive_begin;
                    fault = 1'b0;
                    edges(8);
                    tick_run = 1'b0;
                    edges(2);
                end
                4: begin                                   // reset in the middle of a window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges(q1 * tdiv);
                    drive_begin;
                    tick_run = 1'b0;
                    reset_n = 1'b0;
                    edges(120);
                    reset_n = 1'b1;
                    edges(8);
                end
                5: begin                                   // PWM_START kept high through the window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    drive_begin;
                    pwm_start = 1'b1;                      // never withdrawn here
                    edges(2);
                    blank = 1'b0;
                    tick_div = tdiv;
                    tick_run = 1'b1;
                    edges((intervals + 6) * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    blank = 1'b1;
                    drive_begin;
                    pwm_start = 1'b0;
                    edges(2);
                end
                6: begin                                   // ticks while blank=1 and before PWM_START
                    drive_begin;
                    tick_div = tdiv;
                    tick_run = 1'b1;                       // still blanked and not armed
                    edges(8 * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                7: begin                                   // mode changed while a window runs
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges((intervals / 2) * tdiv);
                    drive_begin;
                    mode = (m == 0) ? 2'd1 : 2'd0;         // refused: running, and system_en is high
                    edges((intervals / 2 + 6) * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    blank = 1'b1;
                    edges(2);
                end
                8: begin                                   // illegal mode code
                    drive_begin;
                    mode = 2'd2;
                    edges(2);
                    drive_begin;
                    cfg_pure_a = pure_a[7:0]; cfg_pure_b = pure_a[7:0];
                    cfg_ht_a = ht_a[5:0];     cfg_ht_b = ht_a[5:0];
                    cfg_pam_a = pam_a[2:0];   cfg_pam_b = pam_a[2:0];
                    cfg_valid = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    cfg_valid = 1'b0;
                    edges(2);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges((intervals + 4) * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    blank = 1'b1;
                    edges(2);
                end
                9: begin                                   // LATCH with cfg_valid low (incomplete)
                    drive_begin;
                    cfg_pure_a = pure_a[7:0]; cfg_pure_b = pure_a[7:0];
                    cfg_ht_a = ht_a[5:0];     cfg_ht_b = ht_a[5:0];
                    cfg_pam_a = pam_a[2:0];   cfg_pam_b = pam_a[2:0];
                    cfg_valid = 1'b0;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    edges(2);
                    arm_start(40);                         // refused too: nothing was displayed
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges((intervals + 4) * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    blank = 1'b1;
                    edges(2);
                end
                10: begin                                  // LATCH on the same edge as the config
                    drive_begin;
                    cfg_pure_a = pure_a[7:0]; cfg_pure_b = pure_a[7:0];
                    cfg_ht_a = ht_a[5:0];     cfg_ht_b = ht_a[5:0];
                    cfg_pam_a = pam_a[2:0];   cfg_pam_b = pam_a[2:0];
                    cfg_valid = 1'b1;
                    latch_stb = 1'b1;                      // both rise together: version-ambiguous
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    edges(2);
                    cfg_valid = 1'b0;
                    edges(1);
                    drive_begin;
                    cfg_valid = 1'b1;                      // now a clean sequence
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    cfg_valid = 1'b0;
                    edges(1);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                11: begin                                  // long reference-clock stall after the window
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                    drive_begin;
                    clk_stall = 1'b1;                      // the whole domain freezes for q1 ns
                    #q1;
                    clk_stall = 1'b0;
                    edges(8);
                end
                12: begin                                  // abort, then a fresh legal sequence
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    tick_div = tdiv;
                    drive_begin;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges(q1 * tdiv);
                    drive_begin;
                    blank = 1'b1;
                    tick_run = 1'b0;
                    edges(6);
                    load_and_latch(q1, q1, q1, q1, q2, q2);  // second, valid sequence
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                13: begin                                  // PAM codes 0 and 7 back to back
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_b, pam_a);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                14: begin                                  // black, shortest, last, full, back to back
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                    load_and_latch(q1, q1, q1, q1, pam_a, pam_a);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                15: begin                                  // mixed codes: two channels, common edges
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                16: begin                                  // power-up: blank released but never configured
                    drive_begin;
                    tick_div = tdiv;
                    blank = 1'b0;
                    tick_run = 1'b1;
                    edges(40 * tdiv);
                    tick_run = 1'b0;
                    edges(2);
                    drive_begin;
                    blank = 1'b1;
                    edges(2);
                end
                17: begin                                  // repeated reset pulses, never configured
                    edges(4);
                    drive_begin;
                    reset_n = 1'b0;
                    edges(20);
                    drive_begin;
                    reset_n = 1'b1;
                    edges(4);
                    drive_begin;
                    reset_n = 1'b0;
                    edges(20);
                    drive_begin;
                    reset_n = 1'b1;
                    edges(8);
                end
                18: begin                                  // legal mode change inside the safe phase
                    load_and_latch(pure_a, pure_b, ht_a, ht_b, pam_a, pam_b);
                    arm_start(40);
                    run_window(intervals, tdiv);
                    drive_begin;
                    system_en = 1'b0;                      // a mode change needs the display disabled
                    edges(2);
                    drive_begin;
                    mode = q1[1:0];                        // blank high, nothing running: accepted
                    edges(2);
                    enable_system;
                    if (q1 == 1) begin
                        drive_begin;
                        cfg_pure_a = 8'd0;  cfg_pure_b = 8'd0;
                        cfg_ht_a = ht_b[5:0]; cfg_ht_b = ht_b[5:0];
                        cfg_pam_a = pam_b[2:0]; cfg_pam_b = pam_b[2:0];
                    end else begin
                        drive_begin;
                        cfg_pure_a = pure_a[7:0]; cfg_pure_b = pure_a[7:0];
                        cfg_ht_a = 6'd0;    cfg_ht_b = 6'd0;
                        cfg_pam_a = 3'd0;   cfg_pam_b = 3'd0;
                    end
                    cfg_valid = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    cfg_valid = 1'b0;
                    edges(1);
                    arm_start(40);
                    run_window((q1 == 1) ? 64 : 256, tdiv);
                end
                19: begin                                  // LATCH with an unknown code bus
                    drive_begin;
                    cfg_pure_a = 8'hxx; cfg_pure_b = 8'hxx;
                    cfg_ht_a = 6'hxx;   cfg_ht_b = 6'hxx;
                    cfg_pam_a = 3'hx;   cfg_pam_b = 3'hx;
                    cfg_valid = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b1;
                    edges(2);
                    drive_begin;
                    latch_stb = 1'b0;
                    cfg_valid = 1'b0;
                    edges(1);
                    arm_start(40);
                    run_window(intervals, tdiv);
                end
                default: begin
                    $display("TB-ERROR unknown profile %0d", profile);
                    $fatal(1);
                end
            endcase
        end
    endtask

    initial begin
        if (!$value$plusargs("VEC=%s", vfile)) begin
            $display("TB-ERROR +VEC=<file> is required");
            $fatal(1);
        end
        if (!$value$plusargs("VCD=%s", vcdfile)) begin
            $display("TB-ERROR +VCD=<file> is required");
            $fatal(1);
        end
        fd = $fopen(vfile, "r");
        if (fd == 0) begin
            $display("TB-ERROR cannot open vector file %s", vfile);
            $fatal(1);
        end
        $display("TB-DATA7A vectors=%s", vfile);
        ncases = 0;
        forever begin
            rc = $fscanf(fd, "%d %d %d %d %d %d %d %d %d %d %d %d %d %d",
                         cid, prof, md, pa, pb, ha, hb, pama, pamb, tdiv, p1, p2, p3, p4);
            if (rc != 14) break;
            run_case(cid, prof, md, pa, pb, ha, hb, pama, pamb, tdiv, p1, p2);
            ncases = ncases + 1;
            $display("TB-CASE %0d profile %0d done at %0t", cid, prof, $time);
        end
        $fclose(fd);
        $display("TB-DATA7A cases=%0d ticks=%0d end", ncases, ticks_sent);
        $finish;
    end

    initial begin
        $dumpfile(vcdfile);
        $dumpvars(0, tb_dd1_d7a_gray);
    end

    initial begin
        #500_000_000;                                      // hard watchdog, far beyond any case
        $display("TB-ERROR watchdog expired after %0d cases", ncases);
        $fatal(1);
    end

endmodule
