;; SCH-1 step 4: the previous run proved two things by measurement, not assumption:
;;   * hiCreateDirLib does create the library (microled_cells/.oalib appeared) but returns nil
;;   * schCreate/schCreateWire/schCheck all return nil in `virtuoso -nograph`, and no view is
;;     created -- the schematic-editor context is not loaded in that mode
;; This probe asks, for each candidate loader, whether the functions become defined, without
;; touching anything outside our own library.

printf("SCHK4_BEGIN\n")

printf("G_before %L\n" errset(getd('schCreate)))
printf("G_wire_before %L\n" errset(getd('schCreateWire)))

printf("TRY_ddLoadContext %L\n" errset(ddLoadContext("schematic")))
printf("G_after_dd %L\n" errset(getd('schCreate)))

printf("TRY_hiLoadContext %L\n" errset(hiLoadContext("schematic")))
printf("G_after_hi %L\n" errset(getd('schCreate)))

printf("TRY_loadContext %L\n" errset(loadContext("schematic")))
printf("TRY_schInit %L\n" errset(schInit()))
printf("G_after_schinit %L\n" errset(getd('schCreate)))

printf("CTX_LIST %L\n" errset(ddGetContexts()))
printf("WINDOW_LIST %L\n" errset(hiGetWindowList()))

printf("TRY_schCreate %L\n" errset(schCreate("microled_cells", "sch1_probe", "schematic", "schematic")))
printf("OPEN_AFTER %L\n" errset(dbOpenCellViewByType("microled_cells", "sch1_probe", "schematic", nil, "a")))

printf("SCHK4_END\n")
