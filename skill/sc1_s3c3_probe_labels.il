;; sc1_s3c3_probe_labels.il
;;
;; Two questions section 4 asks before any wiring is written, both answered on the two target views
;; themselves and read-only:
;;  (1) which attribute really carries a wire label's net name in this build. The S3C2 probe never
;;      tested theLabel, so "no label text is readable" was never established. Both spellings are
;;      printed here: lab~>theLabel and dbGetq(lab 'theLabel).
;;  (2) whether schCreateWireLabel exists here, and whether dbTransformPoint applied to a pin
;;      figure's own bBox centre gives the absolute pin point (section 4 requires the real transform,
;;      so the raw transform and both candidate points are printed side by side).
;; NEW_SIMULATION_RUNS = 0. Nothing is written: both views open with mode "r" and are closed unseen.

plLib = "microled_scan_s3c"
plCells = list("sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch")

procedure(plX(p) car(p))
procedure(plY(p) car(cdr(p)))
procedure(plBx1(b) plX(plX(b)))
procedure(plBy1(b) plY(plX(b)))
procedure(plBx2(b) plX(plX(cdr(b))))
procedure(plBy2(b) plY(plX(cdr(b))))
procedure(plCenter(b)
  list(plDivide(plSum(plBx1(b) plBx2(b)) 2.0) plDivide(plSum(plBy1(b) plBy2(b)) 2.0))
)
procedure(plSum(a b) (plus a b))
procedure(plDivide(a b) (divide a b))
procedure(plVal(v) if(v v "NONE"))
procedure(plHas(nm) if(getd(nm) "EXISTS" "NIL"))

procedure(plShowLabel(n lab)
  printf("PL-LABEL %L objType=%L xy=%L purpose=%L net=%L\n"
         n lab~>objType lab~>xy lab~>purpose plVal(if(lab~>net lab~>net~>name nil)))
  printf("PL-LABEL %L theLabel_tilde=%L dbGetq_theLabel=%L dbGet_theLabel=%L label=%L text=%L name=%L\n"
         n plVal(errset(lab~>theLabel)) plVal(errset(dbGetq(lab 'theLabel)))
         plVal(errset(dbGet(lab 'theLabel)))
         plVal(errset(lab~>label)) plVal(errset(lab~>text)) plVal(errset(lab~>name)))
)

printf("PL-BEGIN\n")
printf("PL-API schCreateWireLabel=%L schCreateLabel=%L dbTransformPoint=%L\n"
       plHas('schCreateWireLabel) plHas('schCreateLabel) plHas('dbTransformPoint))
printf("PL-API schCheck=%L hiCheckAndSave=%L dbCreateLabel=%L dbCreateLine=%L dbCreateRect=%L\n"
       plHas('schCheck) plHas('hiCheckAndSave) plHas('dbCreateLabel)
       plHas('dbCreateLine) plHas('dbCreateRect))

foreach(cell plCells
  cv = car(errset(dbOpenCellViewByType(plLib cell "schematic" "schematic" "r")))
  ;; cv~>insts and cv~>wireFigures answer with an empty list in this build (the same trap as
  ;; cv~>terms vs cv~>terminals); the accessors that carry data are cv~>instances and the wire
  ;; shapes themselves. Re-probed here because the editor packages may only be present once a
  ;; schematic view is actually open.
  printf("PL-API2-after-open schCheck=%L hiCheckAndSave=%L schCreateWireLabel=%L\n"
         plHas('schCheck) plHas('hiCheckAndSave) plHas('schCreateWireLabel))
  printf("PL-VIEW %L opened=%L nets=%L insts=%L instances=%L shapes=%L wireFigures=%L\n"
         cell plVal(cv) length(cv~>nets) length(cv~>insts) length(cv~>instances)
         length(cv~>shapes) length(cv~>wireFigures))
  nl = 0
  nw = 0
  foreach(f cv~>shapes
    when(or(equal(f~>objType "label") equal(f~>objType "wireLabel"))
      nl = nl + 1
      when(lessp(nl 3) plShowLabel(nl f))
    )
    when(or(equal(f~>objType "wire") equal(f~>objType "drawing"))
      nw = nw + 1
      when(lessp(nw 3)
        printf("PL-WIRE %L objType=%L points=%L net=%L\n"
               nw f~>objType f~>points plVal(if(f~>net f~>net~>name nil)))
      )
    )
  )
  printf("PL-VIEW %L label_objects=%L wire_shapes=%L\n" cell nl nw)
  foreach(i cv~>instances
    printf("PL-INST %L objType=%L cell=%L xy=%L transform=%L bBox=%L termFiles=%L\n"
           i~>name i~>objType plVal(i~>cellName) i~>xy i~>transform i~>bBox
           length(i~>terminals))
    foreach(term i~>terminals
      foreach(fig term~>figures
        when(fig~>bBox
          ctr = plCenter(fig~>bBox)
          printf("PL-PIN %L %L %L fig=%L %L bBox=%L center=%L dbTransformPoint=%L direct=%L\n"
                 i~>name plVal(term~>name) term~>direction fig~>objType fig~>purpose
                 fig~>bBox ctr plVal(errset(dbTransformPoint(ctr i~>transform)))
                 plVal(errset(dbTransformPoint(ctr i~>xy))))
        )
      )
    )
  )
  printf("PL-VIEW %L instances_walked=%L\n" cell length(cv~>instances))
  errset(dbClose(cv))
  printf("PL-VIEW %L closed\n" cell)
)
printf("PL-DONE\n")
nil
