; SCH-2 Part I: reach Cadence's own Spectre netlister.
;
; This build exposes asiNetlist / asiRawNetlist / asiInitialize / asiFinalNetlist and
; nlNetlist / nlCreateDesign / nlCreateFormatter / nlSetOption only on the -restore startup path,
; so this file is run that way (MODE=restore bash scripts/sch_virtuoso.sh ... ) with the working
; directory still cadence_work, otherwise the library map does not contain microled_cells (that is
; exactly what made the first attempt open nothing).
;
; Every entry point is tried once with its plausible argument shapes and every answer is printed.
; No result is inferred: if nothing writes a netlist file, the phase says
; NATIVE_CADENCE_NETLIST_VERIFICATION: BLOCKED and keeps its own database reader as the fallback.
;
; Run: SCH1_CELL=c2mos_dff_1bit_paramfix MODE=restore bash scripts/sch_virtuoso.sh skill/sch2_native_netlist.il 600 NN_DONE
printf("NN-BEGIN\n")
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit_paramfix")
cv = dbOpenCellViewByType("microled_cells" CELL "schematic" "schematic" "r")
printf("NN-CV %L cell=%L\n" cv CELL)
when(cv
  printf("NN-COUNT instances=%L nets=%L\n" length(dbGet(cv "instances")) length(dbGet(cv "nets")))
)

s0 = errset(asiCreateSession())
printf("NN-S0 %L\n" s0)
s1 = errset(asiCreateSession(? cellView cv))
printf("NN-S1 %L\n" s1)
s2 = errset(asiCreateSession(? lib "microled_cells" ?cell CELL ?view "schematic"))
printf("NN-S2 %L\n" s2)
sess = car(s0)
unless(sess  sess = car(s1))
unless(sess  sess = car(s2))
printf("NN-SESSION %L\n" sess)
when(sess
  printf("NN-INIT %L\n" errset(asiInitialize(sess)))
  printf("NN-NETLIST %L\n" errset(asiNetlist(sess)))
  printf("NN-FINAL %L\n" errset(asiFinalNetlist(sess)))
)

d1 = errset(nlCreateDesign(cv))
printf("NN-D1 %L\n" d1)
d2 = errset(nlCreateDesign(? libName "microled_cells" ?cellName CELL ?viewName "schematic" ?simulator "spectre"))
printf("NN-D2 %L\n" d2)
d3 = errset(nlCreateDesign("microled_cells" CELL "schematic"))
printf("NN-D3 %L\n" d3)
f1 = errset(nlCreateFormatter(? simulator "spectre"))
printf("NN-F1 %L\n" f1)
f2 = errset(nlCreateFormatter(? simulator "spectre" ?designFormat "spectre"))
printf("NN-F2 %L\n" f2)
design = car(d1)
unless(design  design = car(d2))
unless(design  design = car(d3))
when(design
  printf("NN-NL-A %L\n" errset(nlNetlist(design)))
  when(car(f1)  printf("NN-NL-B %L\n" errset(nlNetlist(design car(f1)))))
  when(car(f2)  printf("NN-NL-C %L\n" errset(nlNetlist(design car(f2)))))
)
printf("NN-FILES %L\n" errset(system("cd /root/microled_ai_project/cadence_work; ls -l *.scs netlist* 2>&1 | head -8; find . -name 'input.scs' -newer asg_in 2>/dev/null | head -4")))
when(cv  dbClose(cv))
printf("NN_DONE\n")
exit()
