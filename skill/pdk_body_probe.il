;; DATA-4.5 read-only OA inspection of the teacher smic18mmrf device masters.
;;
;; Question answered: can a plain n33 have its bulk/body driven by a net of our own
;; (vbias_ch), or is its body the global substrate? A 4th model terminal does not answer
;; this -- isolation is a geometry fact -- so the probe dumps, per cell, the layer/purpose
;; content of the layout device master and the label figures that name the terminals.
;;
;; Build-specific syntax found by measurement, not guesswork:
;;   - this SKILL parser rejects "~" (syntax error at the token) but accepts "->"
;;   - dbOpenCellViewByType rejects viewType "maskOnly" (DB-270208) and needs nil
;;   - the working reader is dbAccess -load, driven by skill/run_skill.sh
;;
;; Nothing here writes: every dbOpenCellViewByType uses mode "r", no view is edited, saved
;; or exported, and the PDK tree is fingerprinted before and after by the driver script.

procedure( pkLayer(f)
  sprintf("%L|%L|%L", errset(sprintf("%L", f->layerName)),
                    errset(sprintf("%L", f->purposeName)),
                    errset(sprintf("%L", f->purpose)))
)

procedure( pkDump(cell view)
  let((cv figs names srt labs nm)
    cv = errset(dbOpenCellViewByType("smic18mmrf", cell, view, nil, "r"))
    unless(cv
      printf("  %s %s: OPEN_FAIL\n" cell view)
    )
    when(cv
      printf("  %s %s: TYPE %L TERMS %L\n" cell view errset(cv->viewType) errset(cv->termNames))
      figs = errset(dbGetFigures(cv))
      printf("  %s %s: NFIG %L\n" cell view errset(length(figs)))
      when(figs
        names = nil
        foreach(f figs
          nm = pkLayer(f)
          when(nm
            unless(member(nm, names)
              names = cons(nm, names)
            )
          )
        )
        srt = errset(sort(names, 'stringp))
        when(srt
          names = srt
        )
        foreach(n names
          printf("   LAYER %s %d\n" n length(setof(f figs pkLayer(f) == n)))
        )
        labs = setof(f figs f->objType == 'label)
        foreach(f labs
          printf("   LABEL %L %L %L %L\n" f->layerName f->purpose f->text errset(f->term->name))
        )
      )
    )
  )
)

printf("PDKBODY_BEGIN\n")

probeCells = list("n33", "n33_3t", "n33_ckt", "n33_dnw_ckt", "n33_dnw_4t_ckt",
                  "p33", "n18", "dnw33_ckt_rf")

foreach(c probeCells
  printf("CELL %s\n" c)
  pkDump(c, "layout")
)

printf("PDKBODY_END\n")
