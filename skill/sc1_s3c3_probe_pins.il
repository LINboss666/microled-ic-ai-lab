;; sc1_s3c3_probe_pins.il
;;
;; Where is a sub-instance pin's drawn point, and which accessor actually carries it in this build?
;; Section 4 requires the point to come from the real pin figure through the instance's full
;; transform, so the candidates are measured side by side instead of guessed:
;;   - schTerm~>figures / ~>figs / ~>net  on the parent view
;;   - the master SYMBOL view's terminal~>figures, whose centre is then pushed through
;;     dbTransformPoint(centre, inst~>transform)
;; Also measures whether the schematic editor package (and with it schCheck / schCreateWireLabel)
;; arrives after a drawing call is attempted -- the late-load behaviour sc1_s3c1_apply_dirs.il
;; recorded, re-measured here because section 4 asks for schCreateWireLabel specifically.
;; Runs with every view opened in mode "r"; the one drawing attempt is a deliberately wrong-arity
;; dbCreateRect on a read-only view, which cannot create a figure. NEW_SIMULATION_RUNS = 0.

ppLib = "microled_scan_s3c"
ppMark = "sc1_ls_c1_top_r2d"

procedure(ppVal(v) if(v v "NONE"))
procedure(ppHas(nm) if(getd(nm) "EXISTS" "NIL"))
procedure(ppLen(x) if(x length(x) 0))
procedure(ppCenter(b)
  list(divide(plus(car(car(b)) car(car(cdr(b)))) 2.0)
       divide(plus(car(cdr(car(b))) car(cdr(car(cdr(b))))) 2.0))
)

printf("PP-BEGIN\n")
src = car(errset(dbOpenCellViewByType(ppLib ppMark "schematic" "schematic" "r")))
printf("PP-SRC opened=%L instances=%L\n" ppVal(src) ppLen(src~>instances))
ppXcoreTr = nil
foreach(i src~>instances
  when(not(equal(i~>cellName "iopin"))
    printf("PP-INST %L master=%L transform=%L\n" i~>name i~>cellName i~>transform)
    when(equal(i~>name "Xcore") ppXcoreTr = i~>transform)
    foreach(tm i~>terminals
      printf("PP-TERM %L %L dir=%L figures=%L figs=%L net=%L\n"
             i~>name tm~>name tm~>direction ppLen(tm~>figures) ppLen(tm~>figs)
             ppVal(if(tm~>net tm~>net~>name nil)))
    )
  )
)
errset(dbClose(src))

;; the master symbol of one child: its own pin figures, and the same point pushed through the
;; instance transform of the parent
sym = car(errset(dbOpenCellViewByType(ppLib "sc1_ls_core_r2d" "symbol" "symbol" "r")))
printf("PP-SYM core opened=%L terminals=%L shapes=%L\n"
       ppVal(sym) ppLen(sym~>terminals) ppLen(sym~>shapes))
foreach(stm sym~>terminals
  printf("PP-SYM-TERM %L dir=%L figures=%L figs=%L\n"
         stm~>name stm~>direction ppLen(stm~>figures) ppLen(stm~>figs))
  foreach(f stm~>figures
    printf("PP-SYM-FIG %L %L purpose=%L layer=%L bBox=%L\n"
           stm~>name f~>objType f~>purpose f~>layerName f~>bBox)
    when(f~>bBox
      ctr = ppCenter(f~>bBox)
      printf("PP-SYM-XFORM %L centre=%L instTransform=%L dbTransformPoint=%L plusOrigin=%L\n"
             stm~>name ctr ppVal(ppXcoreTr)
             ppVal(errset(dbTransformPoint(ctr ppXcoreTr)))
             ppVal(errset(list(plus(car(ctr) car(car(ppXcoreTr))))
                              plus(car(cdr(ctr)) car(cdr(car(ppXcoreTr))))))))
    )
  )
)
errset(dbClose(sym))

;; late editor load: attempt a drawing call inside errset, then ask again
w = car(errset(dbOpenCellViewByType(ppLib ppMark "schematic" "schematic" "r")))
printf("PP-LOAD before schCheck=%L schCreateWireLabel=%L schCreateWire=%L\n"
       ppHas('schCheck) ppHas('schCreateWireLabel) ppHas('schCreateWire))
r = errset(dbCreateRect(w list(list(0.0 0.0) list(0.1 0.1))))
printf("PP-LOAD attempt=%L after schCheck=%L schCreateWireLabel=%L schCreateWire=%L\n"
       ppVal(car(r)) ppHas('schCheck) ppHas('schCreateWireLabel) ppHas('schCreateWire))
errset(dbClose(w))
printf("PP-DONE\n")
nil
