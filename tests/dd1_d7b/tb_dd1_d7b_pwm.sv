// DATA-7B single-instance testbench for dd1_d7a_gray_ctrl.
//
// It drives exactly one controller through the frozen load -> LATCH -> PWM_START -> tick protocol and
// dumps the analog-bench-relevant signals so an offline converter can turn the real four-state edges
// into finite-slope PWL stimulus. The DUT is the byte-identical RTL accepted in DATA-7A; nothing in
// here computes a verdict.
//
//   iverilog -g2012 -Wall -o tb.vvp dd1_d7b_pwm.sv ../../rtl/dd1_d7a_gray_ctrl.sv
//   vvp tb.vvp +CASE=D7B-P30-C016 +VCD=trace.vcd
//
// Case names (one trace each, 17 total):
//   D7B-P30-C000/001/002/016/254/255   Pure,  tick every 3  reference periods (30 ns)
//   D7B-P50-C001/255                   Pure,  tick every 5  periods (50 ns)
//   D7B-H120-C00/01/02/62/63           Hybrid, tick every 12 periods (120 ns), pam request 7
//   D7B-H200-C01/63                    Hybrid, tick every 20 periods (200 ns), pam request 7
//   D7B-BLANK / D7B-FAULT              Pure code 16, 30 ns tick, protection asserted at t0+4.5T and
//                                      withdrawn at t0+7.5T, then a fresh load/LATCH/START window
//
// Stimulus discipline is inherited from the accepted DATA-7A testbench: protocol inputs change 2 ns
// after a rising reference edge (8 ns of setup ahead of the edge that samples them), the tick is a
// clock-enable raised 5 ns before the edge that consumes it and held 1 ns past it, and blank or fault
// are asserted asynchronously because that is what the safety case has to exercise.
`timescale 1ns / 1ps

module tb_dd1_d7b_pwm;

    localparam integer TICK_LEAD = 5;
    localparam integer TICK_HIGH = 6;
    localparam integer NS_PURE_FULL   = 256;   // intervals in a full Pure window
    localparam integer NS_HYB_FULL    = 64;    // intervals in a full Hybrid window

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

    dd1_d7a_gray_ctrl dut (
        .clk(clk), .reset_n(reset_n), .system_en(system_en), .tick(tick), .mode(mode),
        .cfg_pure(cfg_pure), .cfg_hyb_time(cfg_ht), .cfg_hyb_pam(cfg_pam),
        .cfg_valid(cfg_valid), .latch_stb(latch_stb), .pwm_start(pwm_start),
        .blank(blank), .fault(fault),
        .data_en(data_en), .data_en_b(data_en_b), .obs_tick(obs_tick),
        .pam_sel(pam_sel), .win_state(win_state), .cfg_version(cfg_version),
        .proto_err(proto_err));

    // ---------------------------------------------------------------- reference clock, 100 MHz
    always #5 clk = ~clk;                       // rising at 5, 15, 25 ... ns

    // ---------------------------------------------------------------- tick clock-enable
    reg     tick_run = 1'b0;
    integer tick_div = 3;
    integer div_ctr = 0;

    always @(negedge clk) begin
        if (!tick_run) begin
            tick = 1'b0;
            div_ctr = 0;
        end else if (div_ctr == 0) begin
            div_ctr = tick_div - 1;
            tick = 1'b1;
            #(TICK_HIGH);
            tick = 1'b0;
        end else begin
            div_ctr = div_ctr - 1;
        end
    end

    // ---------------------------------------------------------------- case selection
    reg [8*64:1]   casename;
    reg [8*256:1]  vcdname;
    integer pure_code, hyb_code, md, tdiv, full_w, profile;
    integer t_ns;

    // ---------------------------------------------------------------- drive helpers
    task automatic edges;
        input integer n;
        integer k;
        begin
            for (k = 0; k < n; k = k + 1) @(posedge clk);
        end
    endtask

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
            cfg_pure = 8'd0; cfg_ht = 6'd0; cfg_pam = 3'd0;
            reset_n = 1'b0;
            edges(120);                            // 1.2 us, above the contract's 1 us minimum
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

    // present a complete load copy on a later edge than the LATCH that consumes it
    task automatic load_and_latch;
        input integer pure_v;
        input integer ht_v;
        input integer pam_v;
        begin
            drive_begin;
            cfg_pure  = pure_v[7:0];
            cfg_ht    = ht_v[5:0];
            cfg_pam   = pam_v[2:0];
            cfg_valid = 1'b1;
            edges(2);
            drive_begin;
            latch_stb = 1'b1;                      // high across exactly one sampling edge
            edges(2);
            drive_begin;
            latch_stb = 0;
            cfg_valid = 0;
            edges(1);
        end
    endtask

    task automatic arm_start;
        begin
            drive_begin;
            pwm_start = 1'b1;
            edges(2);
            drive_begin;
            pwm_start = 1'b0;
            edges(1);
        end
    endtask

    // one complete window: release blank, feed full_w ticks, then blank again
    task automatic run_window;
        input integer full_w;
        input integer div;
        begin
            tick_div = div;
            drive_begin;
            blank = 1'b0;                          // released mid-cycle, ahead of the first tick
            tick_run = 1'b1;
            edges((full_w + 4) * div);
            tick_run = 1'b0;
            edges(2);
            drive_begin;
            blank = 1'b1;
            edges(2);
        end
    endtask

    // aborted window: blank or fault goes up at t0 + 4.5T and comes down at t0 + 7.5T while the tick
    // train keeps running; the rest of the original window is still observed, then a full
    // load -> LATCH -> START -> window sequence proves the recovery path rather than a re-arming
    task automatic run_aborted_window;
        input integer full_w;
        input integer div;
        input integer abort_blank;                 // 1 = BLANK scenario, 0 = FAULT scenario
        input integer t_ns;                        // tick period in ns
        integer t_first;
        begin
            tick_div = div;
            drive_begin;
            blank = 1'b0;
            tick_run = 1'b1;
            @(posedge obs_tick);
            @(posedge clk);                             // t0 = the edge that consumed that tick
            t_first = $time;
            $display("D7B_ABORT_FIRST_TICK case=%0s t0_ps=%0d", casename, t_first * 1000);
            if (abort_blank) begin
                #(9 * t_ns / 2);
                blank = 1'b1;                       // asynchronous protection request
                #(3 * t_ns);
                blank = 1'b0;
            end else begin
                #(9 * t_ns / 2);
                fault = 1'b1;
                #(3 * t_ns);
                fault = 1'b0;
            end
            edges((full_w + 4) * div);              // watch the remainder of the aborted window
            tick_run = 1'b0;
            edges(2);
            drive_begin;
            blank = 1'b1;
            edges(2);
            // recovery: a brand new transaction, same mode and same reference conditions
            load_and_latch(8'd16, 6'd0, 3'd0);
            arm_start;
            run_window(full_w, div);
        end
    endtask

    // ---------------------------------------------------------------- case dispatch
    initial begin
        if (!$value$plusargs("CASE=%s", casename)) begin
            $display("D7B_TB_REFUSED +CASE=<id> is required");
            $finish;
        end
        if (!$value$plusargs("VCD=%s", vcdname)) begin
            $display("D7B_TB_REFUSED +VCD=<path> is required");
            $finish;
        end
        md = 0; tdiv = 3; full_w = NS_PURE_FULL; profile = 0; pure_code = 0; hyb_code = 0; t_ns = 30;
        case (casename)
            "D7B-P30-C000":  begin md = 0; tdiv = 3;  pure_code = 0;   profile = 1; end
            "D7B-P30-C001":  begin md = 0; tdiv = 3;  pure_code = 1;   profile = 1; end
            "D7B-P30-C002":  begin md = 0; tdiv = 3;  pure_code = 2;   profile = 1; end
            "D7B-P30-C016":  begin md = 0; tdiv = 3;  pure_code = 16;  profile = 1; end
            "D7B-P30-C254":  begin md = 0; tdiv = 3;  pure_code = 254; profile = 1; end
            "D7B-P30-C255":  begin md = 0; tdiv = 3;  pure_code = 255; profile = 1; end
            "D7B-P50-C001":  begin md = 0; tdiv = 5;  pure_code = 1;   profile = 1; t_ns = 50; end
            "D7B-P50-C255":  begin md = 0; tdiv = 5;  pure_code = 255; profile = 1; t_ns = 50; end
            "D7B-H120-C00":  begin md = 1; tdiv = 12; hyb_code = 0;    profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 120; end
            "D7B-H120-C01":  begin md = 1; tdiv = 12; hyb_code = 1;    profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 120; end
            "D7B-H120-C02":  begin md = 1; tdiv = 12; hyb_code = 2;    profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 120; end
            "D7B-H120-C62":  begin md = 1; tdiv = 12; hyb_code = 62;   profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 120; end
            "D7B-H120-C63":  begin md = 1; tdiv = 12; hyb_code = 63;   profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 120; end
            "D7B-H200-C01":  begin md = 1; tdiv = 20; hyb_code = 1;    profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 200; end
            "D7B-H200-C63":  begin md = 1; tdiv = 20; hyb_code = 63;   profile = 1;
                                  full_w = NS_HYB_FULL; t_ns = 200; end
            "D7B-BLANK":     begin md = 0; tdiv = 3;  profile = 2; pure_code = 16; t_ns = 30; end
            "D7B-FAULT":     begin md = 0; tdiv = 3;  profile = 3; pure_code = 16; t_ns = 30; end
            default: begin
                $display("D7B_TB_REFUSED unknown +CASE=%s", casename);
                $finish;
            end
        endcase
        if (profile == 0) begin
            $display("D7B_TB_REFUSED case=%s has no profile", casename);
            $finish;
        end

        $dumpfile(vcdname);
        $dumpvars(0, tb_dd1_d7b_pwm);

        power_on_reset;
        set_mode(md);
        enable_system;
        if (md == 0) begin
            load_and_latch(pure_code, 0, 0);
        end else begin
            load_and_latch(0, hyb_code, 7);        // the pam request is fixed at 7 this round
        end
        arm_start;
        if (profile == 1) begin
            run_window(full_w, tdiv);
        end else begin
            run_aborted_window(full_w, tdiv, (profile == 2), t_ns);
        end
        edges(20);
        $display("D7B_TB_DONE case=%s proto_err=%b win_state=%0d version=%0d",
                 casename, proto_err, win_state, cfg_version);
        $finish;
    end

    initial begin : watchdog
        #60_000;                                    // 60 us, beyond the longest aborted sequence
        $display("D7B_TB_TIMEOUT case=%s", casename);
        $fatal(1, "watchdog");
    end
endmodule
