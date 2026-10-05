;; DATA-4.5 OA corroboration: ask the device-master layout geometry itself whether a
;; plain n33 draws any deep-n-well, and compare with the DNW masters. Read-only ("r").
;;
;; dbGetFigures is tried with several argument shapes because this build rejected the
;; bare one-argument form; every call is errset-wrapped so a bad idiom prints nil instead
;; of aborting the run.

printf("PDKWELL_BEGIN\n")

compareCells = list("n33", "n33_ckt", "n33_dnw_ckt", "n33_dnw_4t_ckt", "p33")
wellLayers = list("DNW", "NW", "PW", "PSUB", "AA", "GT", "PPAA", "NPAA", "CT", "DSTR")

foreach(c compareCells
  printf("CELL %s\n" c)
  cv = errset(dbOpenCellViewByType("smic18mmrf", c, "layout", nil, "r"))
  printf("  CV %L\n" cv)
  when(cv
    printf("  ID1 %L\n" errset(length(dbGetFigures(cv, "drawing", "rect", "DNW"))))
    printf("  ID2 %L\n" errset(length(dbGetFigures(cv, "drawing", t, t))))
    printf("  ID3 %L\n" errset(length(cv->figs)))
    printf("  ID4 %L\n" errset(length(dbGetFigures(cv, t, t, t))))
    printf("  ID5 %L\n" errset(length(dbGetFigures(cv, list("drawing"), t, t))))
    printf("  NAME %L\n" errset(sprintf("%L/%L/%L", cv->libName, cv->cellName, cv->viewName)))
    foreach(ln wellLayers
      printf("  FIGS %s rect=%L path=%L poly=%L label=%L\n" ln
             errset(length(dbGetFigures(cv, "drawing", "rect", ln)))
             errset(length(dbGetFigures(cv, "drawing", "path", ln)))
             errset(length(dbGetFigures(cv, "drawing", "polygon", ln)))
             errset(length(dbGetFigures(cv, "drawing", "label", ln))))
    )
  )
)

printf("PDKWELL_END\n")
