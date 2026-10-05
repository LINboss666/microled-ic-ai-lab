;; DATA-4.5 diagnostic #2: find an idiom that can read the smic18mmrf device masters
;; in batch. Print-only, every call wrapped in errset, opens requested with mode "r".

printf("PDKDIAG2_BEGIN\n")
printf("TOOL %L\n" errset(getversion(t)))
printf("LIBPATH %L\n" errset(getShellEnvVar("PWD")))

lib = "smic18mmrf"
cell = errset(ddGetObj(lib, "n33"))
cv = errset(ddGetObj(lib, "n33", "layout"))
printf("DD_CELL %L\n" cell)
printf("DD_CELL_NAME %L\n" errset(cell->name))
printf("DD_CELL_VIEWS %L\n" errset(cell->cellViews))
printf("DD_CELL_VIEWNAMES %L\n" errset(cell->viewNames))
printf("DD_CV %L\n" cv)
printf("DD_CV_TYPE %L\n" errset(cv->viewType))
printf("DD_CV_CLASS %L\n" errset(cv->objType))
printf("DD_CV_FIGS %L\n" errset(length(cv->figs)))

o1 = errset(dbOpenCellViewByType(lib, "n33", "layout", "maskOnly", "r"))
printf("OPEN_MASKONLY %L\n" o1)
o2 = errset(dbOpenCellViewByType(lib, "n33", "layout", nil, "r"))
printf("OPEN_NILTYPE %L\n" o2)
o3 = errset(dbOpenCellViewByType(lib, "n33", "layout", "layout", "r"))
printf("OPEN_LAYOUTTYPE %L\n" o3)
;; every open above asks for mode "r"; nothing here can write into the PDK.
when(o1
  printf("OPEN_MASKONLY_FIGS %L\n" errset(length(dbGetFigures(o1))))
  printf("OPEN_MASKONLY_TERMS %L\n" errset(o1->termNames))
  errset(dbCloseCellView(o1))
)
printf("PDKDIAG2_END\n")
