;; SCH-1 step 7 -- one consolidated diagnostic that settles two things every earlier
;; conclusion depends on, then stops:
;;
;;  (1) does "->" attribute access work at all in this build? Earlier runs printed nil for
;;      cv->instances / lib->path / obj->name. If "->" is dead here, those were measurement
;;      failures, NOT facts about the data, and must not be reported as such.
;;  (2) does starting an editor application (vi is defined) bring the schematic package with
;;      it, i.e. do schCreate/schCheck appear afterwards?
;;
;; Runs after the environment is up because the driver defers it through the CIW prompt loop.

printf("SCHK7_BEGIN\n")

w = errset(car(hiGetWindowList()))
printf("W_OBJ %L\n" w)
printf("W_ARROW_name %L\n" errset(w->name))
printf("W_ARROW_type %L\n" errset(w->type))
printf("W_FUNCCALL car_name %L\n" errset(w->name))
printf("W_GETATTR %L\n" errset(getattr(w 'name)))
printf("W_SEND %L\n" errset(putattr(w 'name nil)))
printf("W_DESCRIBE %L\n" errset(w->describe()))
printf("W_PP %L\n" errset(pprint(w)))

cv = errset(dbOpenCellViewByType("smic18mmrf", "n18", "symbol", nil, "r"))
printf("CV_OBJ %L\n" cv)
printf("CV_arrow_viewType %L\n" errset(cv->viewType))
printf("CV_arrow_cellName %L\n" errset(cv->cellName))
printf("CV_arrow_libName %L\n" errset(cv->libName))
printf("CV_getattr_viewType %L\n" errset(getattr(cv 'viewType)))
printf("CV_fig_count_arrow %L\n" errset(length(cv->figs)))
printf("CV_fig_count_dbGet %L\n" errset(length(dbGetFigures(cv "drawing" "rect" "ACT" "drawing"))))
printf("CV_termNames %L\n" errset(cv->termNames))
errset(dbCloseCellView(cv))

printf("VI_TRY %L\n" errset(vi(?libName "smic18mmrf" ?cellName "n18" ?viewName "symbol" ?viewType "schematic")))
printf("AFTER_VI_G_schCreate %L\n" errset(getd('schCreate) != nil))
printf("AFTER_VI_G_schCheck %L\n" errset(getd('schCheck) != nil))
printf("WINDOWS_AFTER %L\n" errset(hiGetWindowList()))
printf("SCHK7_END\n")
exit()
