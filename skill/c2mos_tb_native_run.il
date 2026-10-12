; c2mos_tb_native_run.il -- Task 1/2/3: drive Cadence's OWN ADE XL netlister + Spectre from the OA
; testbench cell microled_cells/c2mos_dff_tb, in a batch (-restore) session.
;
; Why this file exists and why it uses axl*: measured in skill/c2mos_tb_native_probe.il, under
; MODE=restore on this build,
;   asiCreateSession  nil for all four ?simulator-carrying shapes   (ADE-L is not usable in batch)
;   sim*/nl*          nil everywhere                                 (no APS batch driver)
;   axlCreateSession("tb_session")  -> ("tb_session")               (ADE XL DOES take a session)
; So the only reachable native path is the ADE XL (adexl.cxt) family, whose signatures were read out
; of the installed /opt/IC617/doc/adexlSKILLref: axlSetMainSetupDBLCV(session lib cell view),
; axlGetTests(sdb), axlGetTestToolArgs, axlPutTest(sdb name tool), axlAddOutputSignal,
; axlPutModel/axlSetModelSection, axlRunSimulation(?session), axlGetPointNetlistDir, axlGetLocalResultsDir.
;
; Phases print what they find instead of assuming it: the object handles and the existing tool-arg
; grammar come from the run itself, because "how do I express tran stop=... maxstep=..." must be read
; off this install, not invented. Every step is wrapped in errset (one unguarded error aborts the
; load), all locals are declared, %L only, and the file ends with exit().
;
; The cell is opened mode "r" everywhere. Nothing here writes to c2mos_dff_1bit, to the PDK or to
; analogLib. ADE XL may create its own session/run directories under the working directory; that is
; listed before and after by the caller so the change is visible rather than silent.
;
; Run: SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_tb AUD_MODEL=<path to spe .lib> AUD_SECTION=tt \
;      MODE=restore bash scripts/sch_virtuoso.sh skill/c2mos_tb_native_run.il 540 NR_DONE
printf("NR-BEGIN\n")

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
MODEL_ENV = getShellEnvVar("AUD_MODEL")
MODEL = if(MODEL_ENV MODEL_ENV "NONE_SET")
SECTION_ENV = getShellEnvVar("AUD_SECTION")
SECTION = if(SECTION_ENV SECTION_ENV "tt")
STOP_ENV = getShellEnvVar("AUD_STOP")
STOP = if(STOP_ENV STOP_ENV "960n")
MAXSTEP_ENV = getShellEnvVar("AUD_MAXSTEP")
MAXSTEP = if(MAXSTEP_ENV MAXSTEP_ENV "20p")
SAVE_ENV = getShellEnvVar("AUD_SAVE")
SAVELIST = parseString(if(SAVE_ENV SAVE_ENV "clk d q qbar") " ")
TESTNAME_ENV = getShellEnvVar("AUD_TEST")
TESTNAME = if(TESTNAME_ENV TESTNAME_ENV "tran1")

procedure(nr(tag expr)
  printf("NR %L -> %L\n" tag expr)
)

procedure(nrBody()
 sess = car(errset(axlCreateSession("tb_session")))
 printf("NR-SESSION %L\n" sess)

; Measured in the first attempt of this file: axlSetMainSetupDBLCV alone returns nil even though the
; session exists, and every later call then has no setup db to work on. The documented
; axlNewSetupDBLCV(t_lib t_cell t_view) creates the setup database for a design, so it is tried
; BEFORE the binding. Both answers are printed; which one is required is what this run measures.
nr("axlNewSetupDBLCV" errset(axlNewSetupDBLCV(LIB CELL "schematic")))
sdb = car(errset(axlSetMainSetupDBLCV(sess LIB CELL "schematic")))
printf("NR-MAINSETUPDB %L\n" sdb)
nr("axlGetMainSetupDB" errset(axlGetMainSetupDB(sess)))
nr("axlGetTests" errset(axlGetTests(sdb)))
nr("axlGetEnabledTests" errset(axlGetEnabledTests(sdb)))
nr("axlGetCorners" errset(axlGetCorners(sdb)))
nr("axlGetActiveSetup" errset(axlGetActiveSetup(sdb)))
nr("axlGetSetupInfo" errset(axlGetSetupInfo(sdb)))
nr("axlGetRunModes" errset(axlGetRunModes(sdb)))
nr("axlGetResultsLocation" errset(axlGetResultsLocation(sdb)))

; what a freshly attached design already contains -- this is where the analysis grammar comes from
tests = car(errset(axlGetTests(sdb)))
printf("NR-TESTS-RAW %L\n" tests)
when(tests
  foreach(t tests
    printf("NR-TEST name=%L\n" t)
    nr("  toolArgs" errset(axlGetTestToolArgs(sess t)))
    nr("  testHandle" errset(axlGetTest(sdb t)))
    nr("  enabled" errset(axlGetEnabled(sdb t)))
  )
)

; ---- build the tran test if the design does not have one yet ----
tr = car(errset(axlPutTest(sdb TESTNAME "spectre")))
printf("NR-PUTTEST %L\n" tr)
nr("axlSetTestToolArgs-list" errset(axlSetTestToolArgs(tr list(list("tran" list("stop" STOP "maxstep" MAXSTEP))))))
nr("axlSetTestToolArgs-flat" errset(axlSetTestToolArgs(tr list("tran" list("stop" STOP "maxstep" MAXSTEP)))))
nr("axlToolSetSetupOptions" errset(axlToolSetSetupOptions(sess TESTNAME list(list("tran" list("stop" STOP "maxstep" MAXSTEP))))))
nr("after-set toolArgs" errset(axlGetTestToolArgs(sess TESTNAME)))
nr("axlSetEnabled" errset(axlSetEnabled(sdb TESTNAME t)))

; ---- save signals ----
foreach(sig SAVELIST
  nr("addOutputSignal" errset(axlAddOutputSignal(sess TESTNAME sig ?save t)))
  nr("addOutputSignal-plain" errset(axlAddOutputSignal(sess TESTNAME sig)))
)
nr("axlAddOutputs" errset(axlAddOutputs(SAVELIST)))

; ---- model file + section (PDK include) ----
corners = car(errset(axlGetCorners(sdb)))
printf("NR-CORNERS-RAW %L\n" corners)
when(corners
  foreach(c corners
    printf("NR-CORNER %L\n" c)
    nr("  getModels" errset(axlGetModels(c)))
    when(MODEL != "NONE_SET"
      mh = car(errset(axlPutModel(c MODEL ?testName TESTNAME)))
      printf("NR-PUTMODEL %L -> %L\n" MODEL mh)
      when(mh
        nr("  setModelSection" errset(axlSetModelSection(mh SECTION)))
        nr("  getModelSection" errset(axlGetModelSection(mh)))
      )
    )
  )
)
nr("axlCommitSetupDB" errset(axlCommitSetupDB(sdb)))

; ---- run it ----
printf("NR-PRE-RUN-LISTING %L\n" errset(system("cd /root/microled_ai_project/cadence_work; ls -A | head -20")))
rid = car(errset(axlRunSimulation(?session sess)))
printf("NR-RUNID %L\n" rid)
; SKILL on this build: poll with for() + eq(), not while() -- and sleep through system(), because
; dbAccess SKILL has no clock of its own (AGENTS.md pitfall 7). Polling is skipped when the run was
; never started: the first attempt of this file burned 36 polls on a nil runid.
done = nil
when(rid
  for(i 1 36
    when(eq(done nil)
      system("sleep 15")
      done = car(errset(axlRunFinished(sess)))
      printf("NR-POLL %L finished=%L\n" i done)
    )
  )
)
nr("axlGetRunStatus" errset(axlGetRunStatus(sess)))
hist = car(errset(axlGetRunData(sess rid)))
printf("NR-HISTORY %L\n" hist)
hn = car(errset(axlGetHistoryName(hist)))
printf("NR-HISTORY-NAME %L\n" hn)
nr("axlGetLocalResultsDir" errset(axlGetLocalResultsDir(hist)))
nr("axlGetPointNetlistDir" errset(axlGetPointNetlistDir(hist TESTNAME)))
nr("axlGetPointPsfDir" errset(axlGetPointPsfDir(hist TESTNAME)))
nr("axlGetPointRunDir" errset(axlGetPointRunDir(hist TESTNAME)))

 printf("NR-FILES %L\n" errset(system("cd /root/microled_ai_project; find . -newer /tmp/tb_audit/marker_run \\( -name '*.scs' -o -name 'input*' -o -name '*.psf*' -o -name '*.raw' \\) -printf '%TY-%Tm-%Td %TH:%TM %s %p\\n' 2>/dev/null | head -30")))
)

; Three startup paths are still untested for the ADE XL design attach, so the same body is offered
; to each: -restore (measured: session yes / attach nil), the asg batch front end, and a real GUI
; session whose init hook runs after the application framework is up (the runner calls sch1Main()
; when DEFER=1, so AUD_DEFER=1 must be set for that path and the top-level call skipped).
procedure(sch1Main()
 printf("NR-DEFERRED-RUN\n")
 nrBody()
 printf("NR_DONE\n")
 exit()
)

DEFER_ENV = getShellEnvVar("AUD_DEFER")
unless(DEFER_ENV nrBody())
unless(DEFER_ENV printf("NR_DONE\n"))
unless(DEFER_ENV exit())
