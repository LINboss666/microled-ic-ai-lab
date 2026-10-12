; c2mos_ade_readbind_once.il -- C2MOS-ADE-READBIND-01: ONE read-only ADE XL bind attempt.
;
; Exactly one thing is measured here, with the argument shape the installed reference actually
; documents (axlSetMainSetupDBLCV(t_session t_libName t_cellName t_viewName [?mode t_mode]); every
; example in /opt/IC617/doc/adexlSKILLref/sessionIl.html passes an ADE setup view such as "adexl",
; and one example shows ?mode "r"):
;
;     axlSetMainSetupDBLCV(session "microled_cells" "c2mos_dff_tb" "adexl" ?mode "r")
;
; The target call is deliberately NOT wrapped in errset. Last round's lesson was that a nil inside
; errset cannot be told apart from a swallowed exception, so this time Cadence's own message (if any)
; must reach the log. If the call signals, the load aborts there and that abort is the evidence; the
; runner's timeout then reaps the idle process.
;
; Nothing else is allowed and nothing else is attempted: no axlNewSetupDBLCV, no axlPutTest, no
; axlSetTestToolArgs, no axlSetEnabled, no axlCommitSetupDB, no axlRunSimulation, no dbSave, no
; netlist, no simulation, no context loaded via load() (contexts are binary -- reading one as SKILL
; source is what produced last round's bogus "load failed" line). No cellview is opened for writing.
; The only side effect intended is an in-memory session, closed at the end by axlCloseSession.
;
; Discipline: when() not if() for multi-statement bodies (SKILL's if takes exactly three arguments),
; %L only, all locals declared, ends with exit().
;
; Run (once only, headless, 180 s ceiling):
;   SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_tb ADE_RB_VIEW=adexl MODE=restore \
;     bash scripts/sch_virtuoso.sh skill/c2mos_ade_readbind_once.il 180 ADE_RB_DONE
printf("RB-BEGIN\n")

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
VIEW_ENV = getShellEnvVar("ADE_RB_VIEW")
VIEW = if(VIEW_ENV VIEW_ENV "adexl")
SESSION_NAME = "rb_once_session"

printf("RB-TARGET library=%L cell=%L view=%L mode=\"r\" session=%L\n" LIB CELL VIEW SESSION_NAME)

; ---- session creation (in-memory only; measured in earlier rounds to create no files) ----
created = car(errset(axlCreateSession(SESSION_NAME)))
printf("RB-CREATE-SESSION %L\n" created)
printf("RB-STATE-BEFORE axlGetWindowSession=%L axlGetMainSetupDB=%L axlSetupStates=%L\n"
       errset(axlGetWindowSession())
       car(errset(axlGetMainSetupDB(created)))
       car(errset(axlSetupStates(created))))

; ---- THE ONE TARGET CALL, unguarded, exactly once ----
sdb = axlSetMainSetupDBLCV(created LIB CELL VIEW ?mode "r")
printf("RB-RETURN-VALUE %L\n" sdb)

printf("RB-STATE-AFTER axlGetMainSetupDB=%L axlSetupStates=%L axlGetWindowSession=%L\n"
       car(errset(axlGetMainSetupDB(created)))
       car(errset(axlSetupStates(created)))
       errset(axlGetWindowSession()))

; ---- close only the session this task created; nothing else is touched ----
printf("RB-CLOSE-SESSION %L\n" errset(axlCloseSession(SESSION_NAME)))
printf("ADE_RB_DONE\n")
exit()
