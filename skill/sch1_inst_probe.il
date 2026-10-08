;; SCH-1 step 3 -- create our own library, a scratch cell, and try the three plausible ways
;; to place a foundry MOS master. Written after two measurements, not assumptions:
;;   * `x == nil` is FALSE in this SKILL even when x is nil, so every test below uses
;;     truthiness (when/unless) instead of comparing to nil
;;   * funcall by quoted symbol returns nil here (documented in AGENTS.md), so function
;;     existence is established by literal calls whose error text lands in the session log
;;
;; Everything created lives under microled_cells inside cadence_work. The PDK is opened with
;; mode "r" only and is never written.

printf("SCHK3_BEGIN\n")
printf("CWD %L\n" errset(getShellEnvVar("PWD")))

;; hiCreateDirLib refuses a directory that does not exist yet (measured: "*WARNING* The
;; directory ... does not exist" and a nil return), so the driver creates the empty
;; directory first. The no-argument call below is only there to make the build print the
;; real signature into the log instead of guessing it.
printf("USAGE_hiCreateDirLib %L\n" errset(hiCreateDirLib()))
printf("PRE_EXISTING_LIB %L\n" errset(ddGetObj("microled_cells")))
printf("MKLIB %L\n" errset(hiCreateDirLib("microled_cells")))
printf("MKLIB_TECHLIB %L\n" errset(hiCreateDirLib("microled_cells" :techLib "smic18mmrf")))
printf("LIB_AFTER %L\n" errset(ddGetObj("microled_cells")))

printf("CELLS_IN_LIB %L\n" errset(ddGetObj("microled_cells")->cellNames))

printf("PRE_SCHCREATE %L\n" errset(schCreate("microled_cells", "sch1_probe", "schematic", "schematic")))
cv = errset(dbOpenCellViewByType("microled_cells", "sch1_probe", "schematic", nil, "a"))
printf("OPEN_FOR_EDIT %L\n" cv)

when(cv
  printf("A_paramInstByMasterName %L\n"
         errset(dbCreateParamInstByMasterName(cv "smic18mmrf" "n18" "schematic" list(100:100))))
  printf("B_paramInst %L\n"
         errset(dbCreateParamInst(cv "smic18mmrf" "n18" "schematic" list(200:100))))
  printf("C_plainInst_schematicview %L\n"
         errset(dbCreateInst(cv "smic18mmrf" "n18" "schematic" list(300:100))))
  printf("D_plainInst_symview %L\n"
         errset(dbCreateInst(cv "smic18mmrf" "n18" "symbol" list(400:100))))
  printf("E_plainInst_maskonly %L\n"
         errset(dbCreateInst(cv "smic18mmrf" "n18" "maskOnly" list(500:100))))
  printf("F_pcellViaSi %L\n"
         errset(siCreateInstance(cv "smic18mmrf" "n18" list(600:100) "schematic")))
  printf("G_analogLibNmos %L\n"
         errset(dbCreateParamInstByMasterName(cv "analogLib" "nmos" "schematic" list(700:100))))
  printf("DBSAVE %L\n" errset(dbSave(cv)))
  printf("SVCHECK %L\n" errset(schCheck(cv)))
  printf("INST_COUNT %L\n" errset(length(setof(i cv->instances t))))
  errset(dbCloseCellView(cv))
)

printf("SCHK3_END\n")
