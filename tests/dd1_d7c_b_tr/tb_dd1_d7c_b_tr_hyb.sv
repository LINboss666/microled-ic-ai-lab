// DATA-7C-B-TR single-channel hybrid testbench for the accepted dd1_d7a_gray_ctrl.
//
// One instance only. It walks the full accepted protocol once per frame and dumps every input, every
// output and the three attestation buses as a four-state VCD, because that VCD, not this file, is what
// the analogue stimulus is converted from: the PWL waves are built from the recorded edges.
//
// The frames are fixed by tests/dd1_d7c_b_tr/contract.json:
//   B0  cfg_hyb_time 0  pam 000   ->  0 conducting intervals, still 64 ticked intervals
//   L1  cfg_hyb_time 1  pam 000   ->  1
//   M2  cfg_hyb_time 2  pam 011   ->  2
//   F63 cfg_hyb_time 63 pam 111   ->  64 (the accepted RTL maps 63 to FULL_HYB)
//   A   cfg_hyb_time 63 pam 111   ->  HYB-120 only: an asynchronous fault at t0 + 2.5*T + 3 ns,
//                                   held 40 ns, then only START inside blank and 600 ns that must
//                                   stay black
// This testbench computes no verdict. The markers it prints are the plan it drove; the measured
// expectation is rebuilt independently from the VCD plus the input codes.
`timescale 1ns / 1ps

module tb_dd1_d7c_b_tr_hyb;

    localparam integer TICK_LEAD = 5;      // same convention as the accepted DATA-7A bench: the tick
    localparam integer TICK_HIGH = 6;      // is an enable raised 5 ns before the edge that samples it
    localparam integer RESET_EDGES = 110;  // 1.1 us, above the 1 us contract minimum
    localparam integer PREP_EDGES = 50;    // 500 ns of blank, enable-low preparation between frames
    localparam integer FULL_HYB = 64;      // intervals in a Hybrid window, as the accepted RTL does
    localparam integer TICKS_SENT = 69;    // 65 to reach DONE, then at least two more tick pulses

    reg clk = 1'b0;
    reg reset_n = 1'b0;
    reg system_en = 1'b0;
    reg tick = 1'b0;
    reg blank = 1'b1;
    reg fault = 1'b0;
    reg [1:0] mode = 2'd0;
    reg [7:0] cfg_pure = 8'd0;
    reg [5:0] cfg_ht = 6'd0;
    reg [2:0] cfg_pam = 3'd0;
    reg cfg_valid = 1'b0;
    reg latch_stb = 1'b0;
    reg pwm_start = 1'b0;

    wire        data_en, data_en_b, obs_tick;
    wire [2:0]  pam_sel, win_state;
    wire [7:0]  cfg_version, proto_err;

    dd1_d7a_gray_ctrl u_ctrl (
        .clk(clk), .reset_n(reset_n), .system_en(system_en), .tick(tick), .mode(mode),
        .cfg_pure(cfg_pure), .cfg_hyb_time(cfg_ht), .cfg_hyb_pam(cfg_pam),
        .cfg_valid(cfg_valid), .latch_stb(latch_stb), .pwm_start(pwm_start),
        .blank(blank), .fault(fault),
        .data_en(data_en), .data_en_b(data_en_b), .obs_tick(obs_tick),
        .pam_sel(pam_sel), .win_state(win_state), .cfg_version(cfg_version),
        .proto_err(proto_err));

    reg clk_run = 1'b0;
    always begin
        while (!clk_run) begin
            #1;
        end
        #5 clk = ~clk;                     // 100 MHz: rising at 5, 15, 25 ... ns
    end

    reg  tick_run = 1'b0;
    integer tick_div = 12;                 // the tick period is tick_div reference periods: 12 or 20
    integer div_ctr = 0;
    integer ticks_raised = 0;

    always @(negedge clk) begin
        if (!tick_run) begin
            tick = 1'b0;
            div_ctr = 0;
        end else if (div_ctr == 0) begin
            div_ctr = tick_div - 1;
            tick = 1'b1;
            ticks_raised = ticks_raised + 1;
            #(TICK_HIGH);
            tick = 1'b0;
        end else begin
            div_ctr = div_ctr - 1;
        end
    end

    integer group_ns = 120;
    reg [8*128:1] arg;
    reg [8*128:1] dumpname;

    task automatic edges;
        input integer n;
        integer k;
        begin
            for (k = 0; k < n; k = k + 1) @(posedge clk);
        end
    endtask

    // every input change lands 2 ns after a rising edge: 8 ns of setup before the sampling edge
    task automatic drive_begin;
        begin
            @(posedge clk);
            #2;
        end
    endtask

    task automatic power_on_reset;
        begin
            drive_begin;
            blank = 1'b1;
            fault = 1'b0;
            system_en = 1'b0;
            mode = 2'd0;
            tick_run = 1'b0;
            pwm_start = 1'b0;
            latch_stb = 1'b0;
            cfg_valid = 1'b0;
            cfg_pure = 8'd0;
            cfg_ht = 6'd0;
            cfg_pam = 3'd0;
            reset_n = 1'b0;
            edges(RESET_EDGES);
            reset_n = 1'b1;
            edges(2);
        end
    endtask

    task automatic set_hybrid_mode;
        begin
            drive_begin;
            mode = 2'd1;                   // the safe phase: blank high, system_en low, no window
            edges(2);                      // held for at least two reference periods
        end
    endtask

    task automatic enable_system;
        begin
            drive_begin;
            system_en = 1'b1;
            edges(1);
        end
    endtask

    // cfg_valid is low after the reset, rises for one complete load, and the LATCH comes on a later
    // sampling edge, never on the edge that carried the load
    task automatic load_and_latch;
        input integer ht;
        input integer pam;
        begin
            drive_begin;
            cfg_ht = ht[5:0];
            cfg_pam = pam[2:0];
            cfg_valid = 1'b1;
            edges(2);
            drive_begin;
            latch_stb = 1'b1;              // high across exactly one sampling edge
            edges(2);
            drive_begin;
            latch_stb = 1'b0;
            cfg_valid = 1'b0;
            edges(1);
        end
    endtask

    task automatic arm_start;
        begin
            drive_begin;
            pwm_start = 1'b1;
            edges(4);                      // held, but accepted as one rising event only
            drive_begin;
            pwm_start = 1'b0;
            edges(1);
        end
    endtask

    task automatic ticks_for_window;
        begin
            tick_run = 1'b1;
            edges(TICKS_SENT * tick_div);
            tick_run = 1'b0;
            edges(2);
        end
    endtask

    task automatic frame;
        input integer ht;
        input integer pam;
        input integer safety;
        begin
            power_on_reset;
            set_hybrid_mode;
            enable_system;
            load_and_latch(ht, pam);
            arm_start;
            if (safety == 0) begin
                drive_begin;
                blank = 1'b0;              // released ahead of the first tick, mid-cycle
                ticks_for_window;
                drive_begin;
                blank = 1'b1;
            end else begin
                drive_begin;
                blank = 1'b0;
                tick_run = 1'b1;
                @(posedge data_en);        // t0 is the reference edge that consumed the first tick
                $display("MARK safety_t0 %t ticks_raised %0d", $time, ticks_raised);
                #((5 * tick_div * 10) / 2);  // 2.5 tick periods
                #3;                           // plus 3 ns, deliberately off the reference clock edge
                fault = 1'b1;                 // asynchronous: not sampled onto a clock edge
                $display("MARK safety_fault %t ticks_raised %0d", $time, ticks_raised);
                #40;                          // held at least 40 ns
                fault = 1'b0;
                drive_begin;
                blank = 1'b1;               // recovery inside blank: only START, no load, no LATCH
                pwm_start = 1'b1;
                edges(4);
                pwm_start = 1'b0;
                tick_run = 1'b1;            // ticks keep running and must stay black
                edges(60);                  // 600 ns
                tick_run = 1'b0;
                edges(2);
                drive_begin;
                blank = 1'b1;
            end
            edges(PREP_EDGES);              // enable-low preparation and tail before the next frame
            $display("MARK frame ht %0d pam %03b win_state %0d version %0d proto_err %b time %t",
                     ht, pam, win_state, cfg_version, proto_err, $time);
        end
    endtask

    initial begin
        $timeformat(-9, 3, " ns", 12);
        group_ns = $test$plusargs("GROUP200") ? 200 : 120;
        tick_div = group_ns / 10;
        if (tick_div * 10 != group_ns || (tick_div != 12 && tick_div != 20)) begin
            $display("TB-ERROR GROUP must be 120 or 200, got %0d", group_ns);
            $finish;
        end
        // this iverilog build resolves $valueplusarg only at runtime, so the trace name is derived
        // from the group instead: one compiled executable, one deterministic dump per run
        if (group_ns == 200) dumpname = "dd1_d7c_b_tr_hyb_200.vcd";
        else dumpname = "dd1_d7c_b_tr_hyb_120.vcd";
        $dumpfile(dumpname);
        $dumpvars(1, tb_dd1_d7c_b_tr_hyb);
        $display("MARK start group_ns %0d tick_div %0d dump %0s", group_ns, tick_div, dumpname);
        clk_run = 1'b1;
        edges(2);
        frame(0, 0, 0);                     // B0, the black frame
        frame(1, 0, 0);                     // L1
        frame(2, 3, 0);                     // M2
        frame(63, 7, 0);                    // F63, 64 intervals
        if (group_ns == 120) frame(63, 7, 1);   // A, the HYB-120 safety window only
        edges(20);
        $display("MARK end group_ns %0d tick_div %0d ticks_raised %0d proto_err %b time %t",
                 group_ns, tick_div, ticks_raised, proto_err, $time);
        $finish;
    end

endmodule
