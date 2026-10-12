; c2mos_tb_native_probe2.il -- load ONE named SKILL context per run, then re-try the netlist entry
; points, so a context that behaves badly cannot take the other candidates down with it.
;
; Measured context ownership, from dfII/etc/context/64bit (strings over the .cxt files): simui.cxt is
; the only non-adexl context that mentions asiCreateSession; adexl.cxt owns the axl* family;
; asimenv.cxt / mmsimenv.cxt are the ADE-simulation and MMSIM integration layers. Whether loading one
; of them makes asi*/axl* actually WORK in a batch session is exactly what this file measures.
;
; History note so nobody re-learns it the hard way: the earlier run of
; skill/c2mos_tb_native_probe.il looked like a 600 s hang inside load("adexl.cxt"). It was not -- the
; file died at load time on `if(cond a b c)`, because SKILL's if takes exactly three arguments
; ("*Error* if: too many arguments (missing then?)"), and the session then sat at the CIW prompt until
; the runner's timeout reaped it. Multi-statement bodies use when(). Retracted on purpose.
;
; Read-only: mode "r", nothing saved, every call wrapped in errset (one unguarded error aborts the
; load), all locals declared, %L only, ends with exit().
;
; Run (headless, one name at a time, short timeout so a bad context costs minutes not ten):
;   for c in simui asimenv mmsimenv adexl; do AUD_CTXNAME=$c MODE=restore \
;     bash scripts/sch_virtuoso.sh skill/c2mos_tb_native_probe2.il 180 NP2_DONE; done
; Run under the ASG batch front end (third startup path, which does have the schematic generator):
;   cd cadence_work && HOME=$PWD/home asg /root/microled_ai_project/skill/c2mos_tb_native_probe2.il
printf("NP2-BEGIN ctx=%L mode=%L display=%L\n" getShellEnvVar("AUD_CTXNAME")
       getShellEnvVar("MODE") getShellEnvVar("DISPLAY"))

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
CTX_ENV = getShellEnvVar("AUD_CTXNAME")
CTX = if(CTX_ENV CTX_ENV "none")

procedure(np2(tag expr)
  printf("NP2 %L -> %L\n" tag expr)
)

unless(CTX == "none"
  np2("hiLoadContext" errset(hiLoadContext(CTX)))
  np2("ddLoadContext" errset(ddLoadContext(CTX)))
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
printf("NP2-CV cell=%L cv=%L\n" CELL cv)

np2("asiCreateSession" errset(asiCreateSession(?simulator "spectre" ?cellView cv)))
np2("asiCreateSession-lcv" errset(asiCreateSession(?simulator "spectre" ?libName LIB
                                                  ?cellName CELL ?viewName "schematic")))
np2("axlGetWindowSession" errset(axlGetWindowSession()))
np2("axlCreateSession" errset(axlCreateSession("tb_session")))
np2("simSetDesign" errset(simSetDesign(LIB CELL "schematic")))
np2("nlCreateDesign" errset(nlCreateDesign(?libName LIB ?cellName CELL ?viewName "schematic"
                                          ?simulator "spectre" ?appName "ADE")))
np2("schCheck-control" errset(schCheck(cv)))
np2("getd-asi" errset(getd('asiCreateSession)))
np2("getd-axl" errset(getd('axlGetWindowSession)))
np2("getd-sim" errset(getd('simSetDesign)))

when(cv dbClose(cv))
printf("NP2_DONE\n")
exit()
