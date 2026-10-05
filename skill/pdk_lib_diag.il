;; DATA-4.5 diagnostic: can batch SKILL see the teacher smic18mmrf library at all?
;; Read-only: opens nothing for edit, prints object identity and library discovery state.

printf("PDKDIAG_BEGIN\n")
printf("PWD %L\n" errset(getShellEnvVar("PWD")))
printf("HOME %L\n" errset(getShellEnvVar("HOME")))
printf("CDS_LIB_PATH %L\n" errset(getShellEnvVar("CDS_LIB_PATH")))
printf("HIINIT %L\n" errset(hiInit()))
printf("HI_LIBS %L\n" errset(hiGetLibList()))
printf("DM_LIB %L\n" errset(ddGetObj("smic18mmrf")))
printf("DM_CELL %L\n" errset(ddGetObj("smic18mmrf", "n33")))
printf("DM_CELLVIEW %L\n" errset(ddGetObj("smic18mmrf", "n33", "layout")))
printf("CELL_VIEWS %L\n"
       errset(mapcar(lambda((v) v->viewName), ddGetObj("smic18mmrf", "n33")->cellViews)))
cv = errset(dbOpenCellViewByType("smic18mmrf", "n33", "layout", "maskOnly", "r"))
printf("CV %L\n" cv)
printf("CV_CLASS %L\n" errset(cv->objType))
printf("CV_CELLNAME %L\n" errset(cv->cellName))
printf("CV_VIEWTYPE %L\n" errset(cv->viewType))
printf("CV_FIGCOUNT %L\n" errset(length(dbGetFigures(cv))))
printf("PDKDIAG_END\n")
