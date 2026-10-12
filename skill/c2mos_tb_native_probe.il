; c2mos_tb_native_probe.il -- Task 1 capability probe: can Cadence's OWN netlister be driven on this
; build, and if so from which startup path?
;
; What is already measured (not re-derived here):
;   * asiCreateSession returns nil in -nograph and in -restore, with and without ?simulator
;     (skill/sch2_native_netlist.il for the no-?simulator family, skill/c2mos_tb_cdf_audit.il section
;     C for the ?simulator "spectre" family). Those attempts wrote nothing.
;   * the ADE SKILL contexts DO exist on disk: dfII/etc/context/64bit/{adexl,simui}.cxt, and the
;     adexl SKILL reference is installed under /opt/IC617/doc/adexlSKILLref (axlCreateSession,
;     axlGetWindowSession, axlRunSimulation, axlAddOutputSignal, axlGetPointNetlistDir ...).
;   * SCH-1 measured that the Schematic Editor package cannot be pulled into -nograph by
;     hiLoadContext/ddLoadContext variants. That is about "sch*", NOT about adexl, so it is not
;     reused as an assumption: every shape below is tried and prints its own answer.
;
; Read-only: cellviews open mode "r", nothing is saved. Every call is wrapped in errset because one
; unguarded error aborts the whole load (measured twice). All locals declared (an undeclared foreach
; var is global in this SKILL). %L only. In the deferred/GUI path the runner calls sch1Main(), so the
; probe body lives in npRun() and exit() is skipped when AUD_DEFER=1.
;
; headless:  MODE=restore bash scripts/sch_virtuoso.sh skill/c2mos_tb_native_probe.il 600 NP_DONE
; GUI way:   DISPLAY=:0 MODE=gui DEFER=1 AUD_DEFER=1 bash scripts/sch_virtuoso.sh \
;            skill/c2mos_tb_native_probe.il 900 NP_DONE
printf("NP-BEGIN\n")

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
DEFER_ENV = getShellEnvVar("AUD_DEFER")
DO_CTX = getShellEnvVar("AUD_CTX")
TRY_CTX = if(DO_CTX DO_CTX "1")

procedure(npTry(tag expr)
  printf("NP %L -> %L\n" tag expr)
)

procedure(npRun()
  when(TRY_CTX == "1"
    npTry("load-adexl-cxt" errset(load("/opt/IC617/tools.lnx86/dfII/etc/context/64bit/adexl.cxt")))
    npTry("load-simui-cxt" errset(load("/opt/IC617/tools.lnx86/dfII/etc/context/64bit/simui.cxt")))
    npTry("hiLoadContext-adexl" errset(hiLoadContext("adexl")))
    npTry("hiLoadContext-simui" errset(hiLoadContext("simui")))
    npTry("ddLoadContext-adexl" errset(ddLoadContext("adexl")))
  )
  printf("NP-DISPLAY %L\n" getShellEnvVar("DISPLAY"))
  printf("NP-MODE %L\n" getShellEnvVar("MODE"))

  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  printf("NP-CV cell=%L cv=%L instances=%L\n" CELL cv
         car(errset(errset(length(dbGet(cv "instances"))))))

  ; ---- family 1: classic ADE-L (asi*) ----
  npTry("asiCreateSession-sim-cv" errset(asiCreateSession(?simulator "spectre" ?cellView cv)))
  npTry("asiCreateSession-lcv" errset(asiCreateSession(?simulator "spectre" ?libName LIB
                                                      ?cellName CELL ?viewName "schematic")))
  npTry("asiCreateSession-app" errset(asiCreateSession(?simulator "spectre" ?cellView cv
                                                      ?appName "ADE")))
  npTry("asiCreateSession-dir" errset(asiCreateSession(?simulator "spectre" ?cellView cv
                                                      ?tmpDir "/tmp/tb_audit/nl")))
  npTry("asiNetlist-bare" errset(asiNetlist()))
  npTry("asiInitialize-bare" errset(asiInitialize()))

  ; ---- family 2: ADE XL / Plus (axl*), documented in /opt/IC617/doc/adexlSKILLref ----
  npTry("axlGetWindowSession" errset(axlGetWindowSession()))
  npTry("axlCreateSession-named" errset(axlCreateSession("tb_session")))
  npTry("axlCreateSession-q" errset(axlCreateSession(?sessionName "tb_session" ?libName LIB
                                                    ?cellName CELL ?viewName "schematic")))
  npTry("axlMainAppCreateSession" errset(axlMainAppCreateSession("tb_session" LIB CELL "schematic")))
  npTry("axlRunSimulation-bare" errset(axlRunSimulation()))
  npTry("axlGetMainSetupDB" errset(axlGetMainSetupDB()))
  npTry("axlNewSetupDB" errset(axlNewSetupDB()))
  npTry("axlGetRunModes" errset(axlGetRunModes()))
  npTry("axlGetPointNetlistDir" errset(axlGetPointNetlistDir("tb_session" "spectre")))

  ; ---- family 3: APS / sim* batch driver ----
  npTry("simSetDesign" errset(simSetDesign(LIB CELL "schematic")))
  npTry("simSetTool" errset(simSetTool("spectre")))
  npTry("simTestInit" errset(simTestInit()))
  npTry("simRun" errset(simRun()))
  npTry("simGetVariable" errset(simGetVariable("simDir")))

  ; ---- family 4: netlist-only entry points, one extra shape each, plus the editor control ----
  npTry("nlCreateDesign-sim" errset(nlCreateDesign(?libName LIB ?cellName CELL ?viewName "schematic"
                                                  ?simulator "spectre" ?appName "cmdline")))
  npTry("nlCreateFormatter-sim" errset(nlCreateFormatter(?simulator "spectre" ?appName "cmdline")))
  npTry("nlNetlist-bare" errset(nlNetlist()))
  npTry("schCheck-control" errset(schCheck(cv)))
  npTry("dbCheck-control" errset(dbCheck(cv)))
  npTry("hiGetSimulationFileData" errset(hiGetSimulationFileData(cv)))

  when(cv dbClose(cv))
)

procedure(sch1Main()
  printf("NP-DEFERRED-RUN\n")
  npRun()
  printf("NP_DONE\n")
  exit()
)

unless(DEFER_ENV npRun())
unless(DEFER_ENV printf("NP_DONE\n"))
unless(DEFER_ENV exit())
