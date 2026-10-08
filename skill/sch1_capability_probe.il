;; SCH-1 B/C capability probe. Read-only: it opens PDK cell views with mode "r" and asks the
;; running Virtuoso which schematic-side functions exist. It creates nothing.
;;
;; Why: "Spectre has a model named n18" does not prove the OA library can be instantiated,
;; and the DATA-4.5 finding was that this build's SKILL parser rejects "~" (use "->"), while
;; dbAccess could not read geometry at all. So the questions get asked of full Virtuoso.

printf("SCHK_BEGIN\n")
printf("PWD %L\n" errset(getShellEnvVar("PWD")))
printf("HOME %L\n" errset(getShellEnvVar("HOME")))

foreach(n list("smic18mmrf", "analogLib", "basic", "microled_cells")
  printf("LIB %s %L\n" n errset(ddGetObj(n)))
)

lib = errset(ddGetObj("smic18mmrf"))
printf("LIB_PATH %L\n" errset(lib->path))
printf("LIB_NAME %L\n" errset(lib->name))
cells = errset(lib->cellNames)
printf("CELL_COUNT %L\n" errset(length(cells)))
printf("HAS_N18 %L\n" errset(member("n18", cells)))
printf("HAS_P18 %L\n" errset(member("p18", cells)))

foreach(v list("schematic", "symbol", "layout", "spectre", "data", "primitive")
  printf("OPEN n18/%s %L\n" v errset(dbOpenCellViewByType("smic18mmrf", "n18", v, nil, "r")))
)

sv = errset(dbOpenCellViewByType("smic18mmrf", "n18", "symbol", nil, "r"))
printf("SYM_OBJ %L\n" sv)
when(sv
  printf("SYM_TYPE %L\n" errset(sv->viewType))
  figs = errset(dbGetFigures(sv))
  printf("SYM_FIGS %L\n" errset(length(figs)))
  printf("SYM_TERMS %L\n" errset(sv->termNames))
  printf("SYM_LABELS %L\n" errset(length(setof(f figs f->objType == 'label))))
  foreach(f errset(setof(f figs f->objType == 'label))
    printf("  SYM_LABEL %L %L %L\n" f->layerName f->purpose f->text)
  )
  errset(dbCloseCellView(sv))
)

foreach(fn list('schCreate, 'schCreateWire, 'schCreatePin, 'schCreateRect, 'dbCreateInst,
                'dbCreateTerm, 'schCheck, 'schDelete, 'hiCheckAndSave, 'dbCreateLib,
                'ddCreateLib, 'hiCreateDirLib, 'hiCreateNetlistLib, 'hiGetTechnologies,
                'dbGetTechName, 'schUseTechFile, 'hiGetWindowList, 'dbCreateCell,
                'dbOpenCellViewByType, 'hiSourceFile, 'schSelectAllWithMark, 'dbGetInst)
  printf("HASFN %s %L\n" fn errset(getd(fn) != nil))
)

printf("SCHK_END\n")
