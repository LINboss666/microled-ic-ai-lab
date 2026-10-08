;; SCH-1 step 6 -- the ordering fix, plus honest existence tests.
;;
;; Why: every previous call happened while .cdsinit was still running, i.e. before any
;; application package had been started, and `errset()` hides "undefined function" so a nil
;; return proved nothing. getd is also unreliable here (it reported hiCreateDirLib nil, yet
;; that call really did create microled_cells/.oalib). So:
;;   * the driver sets this as hiSetInitFunc, and sch1Main runs after the environment is up
;;   * each function is first tried inside errset (so the run survives), then, if that gave
;;     nil, called BARE so the session log records the real error text
;;   * nothing is created outside microled_cells; the probe cell name is checked first

printf("SCHK6_LOADED\n")

procedure( sch1Main()
  printf("SCHK6_BEGIN\n")
  printf("DEFERRED_RAN t\n")
  printf("G_schCreate %L\n" errset(getd('schCreate) != nil))
  printf("G_schCheck %L\n" errset(getd('schCheck) != nil))
  printf("G_hiCheckAndSave %L\n" errset(getd('hiCheckAndSave) != nil))
  printf("G_ddCreateCellView %L\n" errset(getd('ddCreateCellView) != nil))

  ;; 1) does a cell + schematic view come into existence at DB level?
  cell = errset(ddCreateCell("microled_cells", "sch1_probe"))
  printf("DD_CREATE_CELL %L\n" cell)
  cell = errset(ddGetObj("microled_cells", "sch1_probe"))
  printf("CELL_OBJ %L\n" cell)
  cvd = errset(ddCreateCellView(cell, "schematic", "schematic"))
  printf("DD_CREATE_CELLVIEW %L\n" cvd)
  cv = errset(dbOpenCellViewByType("microled_cells", "sch1_probe", "schematic", nil, "a"))
  printf("DB_OPEN_APPEND %L\n" cv)

  when(cv
    ;; 2) one instance, both plausible master-view spellings
    i1 = errset(dbCreateParamInstByMasterName(cv "smic18mmrf" "n18" "schematic" list(100:100)))
    printf("PARAM_BY_MASTER_NAME %L\n" i1)
    i2 = errset(dbCreateInst(cv "smic18mmrf" "n18" "schematic" list(200:100)))
    printf("DB_CREATE_INST %L\n" i2)
    printf("INST_NOW %L\n" errset(length(cv->instances)))
    printf("SAVED %L\n" errset(dbSave(cv)))
    errset(dbCloseCellView(cv))
  )

  ;; 3) bare calls, only to make the log name the failure precisely
  printf("BARE_schCreate_start\n")
  errset(schCreate("microled_cells", "sch1_probe2", "schematic", "schematic"))
  printf("BARE_schCreate_end %L\n" errset(dbOpenCellViewByType("microled_cells", "sch1_probe2", "schematic", nil, "r")))
  printf("SCHK6_END\n")
  exit()
)
