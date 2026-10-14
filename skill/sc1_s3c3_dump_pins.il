;; sc1_s3c3_dump_pins.il
;;
;; Everything the two parent views need before a wire is drawn, printed straight out of the database.
;; Accessors are the ones sc1_s3c1_geom_dump.il proved carry data -- i~>instTerms, tm~>pins~>figs --
;; and no arithmetic happens here: `divide` does not exist in this SKILL build (measured), so both
;; transformed corners are printed and the midpoint is taken by the Python reader.
;;
;; For every sub-instance pin the pair of corners is printed twice:
;;   - RAW      = the master symbol's own pin figure box, in symbol coordinates
;;   - XFORMED  = the same two points pushed through dbTransformPoint with the instance transform,
;;                which is the absolute parent point section 4 asks for (nothing subtracted).
;; Also measures which attribute of an instTerm exposes its pin figure, because it~>figure answered
;; NONE. Views open read-only. NEW_SIMULATION_RUNS = 0.

dpLib = "microled_scan_s3c"
dpViews = list("sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_scan_power_1ch_s3c"
               "s3c3_ls_copy" "s3c3_chain_copy")

procedure(dpVal(v) if(v v "NONE"))
procedure(dpLen(x) if(x length(x) 0))
procedure(dpGet(o nm) car(errset(dbGet(o nm))))
procedure(dpFirstCorner(b) if(b car(b) nil))
procedure(dpSecondCorner(b) if(b car(cdr(b)) nil))

procedure(dpSymPinBoxes(cellName)
  ;; ((termName corner1 corner2) ...) of one symbol view's pin figures
  let((res cv)
    res = nil
    cv = car(errset(dbOpenCellViewByType(dpLib cellName "symbol" nil "r")))
    when(cv
      foreach(tm cv~>terminals
        foreach(p tm~>pins
          foreach(f p~>figs
            when(f~>bBox
              res = cons(list(tm~>name dpFirstCorner(f~>bBox) dpSecondCorner(f~>bBox)
                                f~>objType f~>purpose f~>layerName) res)
            )
          )
        )
      )
      errset(dbClose(cv))
    )
    res
  )
)

procedure(dpLookup(boxes name)
  let((hit)
    hit = nil
    foreach(item boxes
      when(and(hit == nil equal(car(item) name)) hit = item)
    )
    hit
  )
)

printf("DP-BEGIN\n")
foreach(view dpViews
  cv = car(errset(dbOpenCellViewByType(dpLib view "schematic" nil "r")))
  printf("DP-VIEW %L opened=%L nets=%L instances=%L terminals=%L shapes=%L\n"
         view dpVal(cv) dpLen(cv~>nets) dpLen(cv~>instances) dpLen(cv~>terminals)
         dpLen(cv~>shapes))
  foreach(i cv~>instances
    boxes = dpSymPinBoxes(i~>cellName)
    printf("DP-INST %L %L master=%L transform=%L bBox=%L instTerms=%L symPinBoxes=%L\n"
           view i~>name dpVal(i~>cellName) i~>transform i~>bBox dpLen(i~>instTerms)
           dpLen(boxes))
    foreach(it i~>instTerms
      printf("DP-ITERM %L %L %L dir=%L net=%L figure=%L figs=%L pinFigs=%L objType=%L\n"
             view i~>name dpVal(it~>name) dpVal(it~>direction)
             dpVal(if(it~>net it~>net~>name nil)) dpVal(dpGet(it 'figure))
             dpVal(dpGet(it 'figs)) dpVal(dpGet(it 'pinFig)) dpVal(it~>objType))
      hit = dpLookup(boxes it~>name)
      when(hit
        c1 = car(cdr(hit))
        c2 = car(cdr(cdr(hit)))
        printf("DP-PIN %L %L %L RAW %L %L XFORMED %L %L purpose=%L layer=%L\n"
               view i~>name car(hit) c1 c2
               dpVal(car(errset(dbTransformPoint(c1 i~>transform))))
               dpVal(car(errset(dbTransformPoint(c2 i~>transform))))
               car(cdr(cdr(cdr(cdr(hit))))) car(cdr(cdr(cdr(cdr(cdr(hit))))))))
    )
  )
  foreach(tm cv~>terminals
    foreach(p tm~>pins
      foreach(f p~>figs
        printf("DP-PORT %L %L dir=%L net=%L fig=%L %L bBox=%L\n"
               view tm~>name tm~>direction dpVal(if(tm~>net tm~>net~>name nil))
               f~>objType f~>purpose f~>bBox)
      )
    )
  )
  foreach(n cv~>nets
    printf("DP-NET %L %L figs=%L\n" view n~>name dpLen(n~>figs))
  )
  foreach(f cv~>shapes
    when(or(equal(f~>objType "label") equal(f~>objType "wireLabel"))
      printf("DP-LABEL %L %L theLabel=%L xy=%L net=%L just=%L\n"
             view f~>objType dpVal(car(errset(f~>theLabel))) f~>xy
             dpVal(if(f~>net f~>net~>name nil)) dpVal(f~>justification)))
  )
  ;; every wire figure with its real vertices and the net the database put it on. Section 6 requires
  ;; the pin-point check to run on these segments, not on a bounding box.
  foreach(f cv~>shapes
    when(and(equal(f~>layerName "wire")
             or(equal(f~>objType "line") equal(f~>objType "wire") equal(f~>objType "path")))
      printf("DP-WIRE %L objType=%L net=%L points=%L bbox=%L\n"
             view f~>objType dpVal(if(f~>net f~>net~>name nil)) f~>points f~>bBox)
    )
  )
  errset(dbClose(cv))
)
printf("DP-DONE\n")
nil
