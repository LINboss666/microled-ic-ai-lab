;; SCH-1 Part C: spiceIn (ASG) parameter file.
;; The golden cell is a `subckt`, but spiceIn's default top cell name is the literal string
;; "top"; with that default it reads the `subckt c2mos_dff_1bit (d clk q qbar vdd vss)` line as
;; an instance and takes `vss` as its master (spiceIn.log line 27-42). Declaring the real top
;; cell name is the only change this file makes.
envSetVal("spiceIn" "topCell" 'string "c2mos_dff_1bit")
