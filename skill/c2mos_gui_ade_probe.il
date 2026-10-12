; c2mos_gui_ade_probe.il -- READ-ONLY probe: in a real GUI session, does Virtuoso IC617 actually
; initialise the ADE / Spectre netlisting capability that answered nil under -restore?
;
; This file contains NONE of the write-side ADE operations the task book forbids: no axlPutTest, no
; axlSetTestToolArgs, no axlSetEnabled, no axlCommitSetupDB, no axlRunSimulation -- and no dbSave,
; dbCreateProp or cdfSetParamValue either. Cellviews open mode "r". Design *attach*
; (axlSetMainSetupDBLCV) is queried because the task book asks specifically whether the entry that
; returned nil under -restore still returns nil after a real GUI initialisation; the caller takes a
; file manifest of microled_cells before and after, so if attach ever creates an object that is
; caught and reported rather than quietly accepted.
;
; The classification the task book demands -- API missing / wrong arguments / session not
; initialised / design-bind failure / licence / display -- is separated by CONTROLS rather than by
; interpretation:
;   * schCheck(cv) is the editor-package control, measured working in the GUI path (AGENTS.md rule
;     28). If it answers, the Schematic Editor really initialised, so a nil from an ADE entry is an
;     ADE statement and not "the session never started".
;   * getd('<name>) is printed beside every call to separate "no such function here" from
;     "function exists, call failed" -- with the measured caveat that getd itself lies on some
;     startup paths, so the call answer stays the primary signal.
;   * the caller separately proves a real window with xprop (Map State / WM_STATE) taken with the
;     GNOME session's own environment, because "a process exists" is not "the GUI appeared".
;
; Both startup times inside a GUI session are exercised, because they are different questions:
;   .cdsinit time  : AUD_DEFER unset  -> gapBody() runs from the injected .cdsinit
;   after init     : AUD_DEFER=1 + DEFER=1 -> the runner calls sch1Main(), which runs gapBody()
;
; Run through the verified launch chain (no new environment loader is invented here):
;   bash scripts/gui2_envexec.sh env MODE=gui \
;        bash scripts/sch_virtuoso.sh skill/c2mos_gui_ade_probe.il 300 GAP_DONE
;
; Discipline: car(errset(x)) (errset returns a LIST), %L only, loop variables declared, "t" never a
; name, when() for multi-statement bodies because SKILL's if() takes exactly three arguments.
printf("GAP-BEGIN\n")

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
DUT_ENV = getShellEnvVar("GAP_DUT")
DUT = if(DUT_ENV DUT_ENV "c2mos_dff_1bit")

procedure(gap(tag expr)
  printf("GAP %L -> %L\n" tag expr)
)

procedure(gapBody()
  printf("GAP-ENV DISPLAY=%L MODE=%L DEFER=%L\n" getShellEnvVar("DISPLAY")
         getShellEnvVar("MODE") getShellEnvVar("AUD_DEFER"))
  printf("GAP-XAUTH %L\n" getShellEnvVar("XAUTHORITY"))

  ; ---- A. controls: is this a windowed, editor-initialised session? ----
  mwin = errset(hiGetMainWindow())
  printf("GAP-HI-MAINWINDOW %L\n" mwin)
  cv0 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  printf("GAP-SCHCHECK-CONTROL %L open=%L\n" errset(schCheck(cv0)) cv0)

  ; ---- B. does each entry point exist in THIS session? ----
  gap("getd-asiCreateSession" errset(getd('asiCreateSession)))
  gap("getd-asiNetlist" errset(getd('asiNetlist)))
  gap("getd-axlCreateSession" errset(getd('axlCreateSession)))
  gap("getd-axlGetWindowSession" errset(getd('axlGetWindowSession)))
  gap("getd-axlSetMainSetupDBLCV" errset(getd('axlSetMainSetupDBLCV)))
  gap("getd-simSetDesign" errset(getd('simSetDesign)))
  gap("getd-nlCreateDesign" errset(getd('nlCreateDesign)))

  ; ---- C. read the design: the testbench schematic and the DUT symbol ----
  printf("GAP-TB-OPEN cell=%L cv=%L instances=%L nets=%L terms=%L\n" CELL cv0
         car(errset(errset(length(dbGet(cv0 "instances")))))
         car(errset(errset(length(dbGet(cv0 "nets")))))
         car(errset(errset(length(cv0->terms)))))
  sv = dbOpenCellViewByType(LIB DUT "symbol" nil "r")
  sytm = car(errset(sv->terminals))
  printf("GAP-DUT-SYMBOL cell=%L open=%L terminals=%L\n" DUT sv
         if(sytm car(errset(errset(length(sytm)))) "nil"))
  when(sytm
    foreach(tm sytm
      printf("GAP-DUT-SYMPIN name=%L dir=%L\n" car(errset(tm->name)) car(errset(tm->direction)))
    )
  )
  when(sv dbClose(sv))

  ; ---- D. ADE-L (asi*) in a windowed session ----
  s1 = errset(asiCreateSession(?simulator "spectre" ?cellView cv0))
  printf("GAP-ASI-1 %L\n" s1)
  s2 = errset(asiCreateSession(?simulator "spectre" ?libName LIB ?cellName CELL
                               ?viewName "schematic"))
  printf("GAP-ASI-2 %L\n" s2)
  sessA = car(s1)
  unless(sessA sessA = car(s2))
  printf("GAP-ASI-SESSION %L\n" sessA)
  when(sessA
    printf("GAP-ASI-INIT %L\n" errset(asiInitialize(sessA)))
    printf("GAP-ASI-NETLIST %L\n" errset(asiNetlist(sessA)))
  )

  ; ---- E. ADE XL (axl*) attach, then read-only queries only ----
  sess = car(errset(axlCreateSession("probe_session")))
  printf("GAP-AXL-SESSION %L\n" sess)
  printf("GAP-AXL-GET-WS %L\n" errset(axlGetWindowSession()))
  sdb = car(errset(axlSetMainSetupDBLCV(sess LIB CELL "schematic")))
  printf("GAP-AXL-ATTACH %L\n" sdb)
  when(sdb
    printf("GAP-AXL-TESTS %L\n" errset(axlGetTests(sdb)))
    printf("GAP-AXL-CORNERS %L\n" errset(axlGetCorners(sdb)))
    printf("GAP-AXL-RESULTSLOCATION %L\n" errset(axlGetResultsLocation(sdb)))
  )

  ; ---- F. is the failure "ADE context not loaded" rather than "ADE cannot bind"? Measured fact: a
  ; mapped GUI session loads 16 contexts and adexl/simui/asimenv/mmsimenv are NOT among them, so the
  ; nil above may simply be an unloaded package. Load them explicitly (read-only: a context is code,
  ; loading it writes nothing) and re-ask the same questions. ----
  LOAD_ENV = getShellEnvVar("AUD_LOAD")
  when(LOAD_ENV == "1"
    printf("GAP-LOAD-hiLoadContext-simui %L\n" errset(hiLoadContext("simui")))
    printf("GAP-LOAD-hiLoadContext-adexl %L\n" errset(hiLoadContext("adexl")))
    printf("GAP-LOAD-load-cxt-simui %L\n"
           errset(load("/opt/IC617/tools.lnx86/dfII/etc/context/64bit/simui.cxt")))
    printf("GAP-LOAD-load-cxt-adexl %L\n"
           errset(load("/opt/IC617/tools.lnx86/dfII/etc/context/64bit/adexl.cxt")))
    printf("GAP-AFTER-ASI-EXIST %L\n" errset(getd('asiCreateSession)))
    printf("GAP-AFTER-ASI-NL-EXIST %L\n" errset(getd('asiNetlist)))
    printf("GAP-AFTER-NL-EXIST %L\n" errset(getd('nlCreateDesign)))
    printf("GAP-AFTER-SIM-EXIST %L\n" errset(getd('simSetDesign)))
    printf("GAP-AFTER-AXL-BIND-EXIST %L\n" errset(getd('axlSetMainSetupDBLCV)))
    printf("GAP-AFTER-ASI-CALL %L\n" errset(asiCreateSession(?simulator "spectre" ?cellView cv0)))
    printf("GAP-AFTER-AXL-CALL %L\n" errset(axlCreateSession("probe_session2")))
    sess2 = car(errset(axlCreateSession("probe_session2")))
    printf("GAP-AFTER-ATTACH %L\n" errset(axlSetMainSetupDBLCV(sess2 LIB CELL "schematic")))
  )

  when(cv0 dbClose(cv0))
)

procedure(sch1Main()
  printf("GAP-DEFERRED-RUN\n")
  gapBody()
  printf("GAP_DONE\n")
  exit()
)

DEFER_ENV = getShellEnvVar("AUD_DEFER")
unless(DEFER_ENV gapBody())
unless(DEFER_ENV printf("GAP_DONE\n"))
unless(DEFER_ENV exit())
