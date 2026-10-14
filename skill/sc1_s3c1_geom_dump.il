;; sc1_s3c1_geom_dump.il
;;
;; SCAN-1 S3C1 -- one read-only geometry dump of all sixteen delivered views, in a fixed line
;; schema, so the placement pass can be computed offline and applied by exact coordinate.
;;
;; Why this is the right primitive: measured in readback/s3c1_probe7.log, assigning fig~>bBox and
;; label~>xy in batch WORKS and survives dbSave + reopen (S7-SETBBOX rc=t changed=t / S7-SAVE t /
;; S7-REOPEN t), while dbMoveFig returned nil in three argument orders and dbCreateRect /
;; dbCreateLine / dbCreateLabel / dbCreatePin returned nil in six forms. So figures that already
;; exist can be PLACED, and no figure has to be created or deleted.
;;
;; Read-only: every view is opened with mode "r" and nothing is dbSave'd. Attributes that a build
;; may not support are read through errset so one missing field cannot abort the dump -- a missing
;; value prints as NONE and is never silently treated as an empty set.
;; NEW_SIMULATION_RUNS = 0.

s9Lib   = "microled_scan_s3c"
s9Cells = list("c2mos_dff" "sc1_scan_gate" "sc1_ls_core_r2d" "sc1_ls_c1_r2d"
               "sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_s3b_p33_bank_7"
               "sc1_scan_power_1ch_s3c")

procedure(s9Get(obj nm)
  car(errset(dbGet(obj nm)))
)

;; NONE for "no value", never a blank, so the parser can tell an absent attribute from a zero
procedure(s9Val(v)
  if(v == nil "NONE" v)
)

;; SKILL's if takes exactly three arguments (measured: "if: tomany arguments (missing then?)"),
;; so a two-branch print with an extra arm is written as two when forms instead.
procedure(s9BBox(f)
  let((b)
    b = f~>bBox
    when(b != nil
      printf("%L %L %L %L" car(car(b)) cadr(car(b)) car(cadr(b)) cadr(cadr(b)))
    )
    when(b == nil
      printf("NONE NONE NONE NONE")
    )
  )
)

procedure(s9Point(p)
  when(p != nil
    printf("%L %L" car(p) cadr(p))
  )
  when(p == nil
    printf("NONE NONE")
  )
)

procedure(s9FigLine(f cell view idx)
  printf("S9|S|%L|%L|%L|%L|%L|%L", cell view idx f~>objType f~>layerName f~>purpose)
  s9BBox(f)
  printf("|%L|%L", s9Val(s9Get(f 'objName)) s9Val(if(f~>net f~>net~>name nil)))
  ;; labels and text placements are moved by their xy anchor
  printf("|%L", s9Val(s9Get(f 'justification)))
  s9Point(s9Get(f 'xy))
  printf("|%L\n" s9Val(s9Get(f 'text)))
)

procedure(s9DumpView(cell view)
  let((cv n)
    cv = car(errset(dbOpenCellViewByType(s9Lib cell view
                                         if(view == "schematic" "schematic" nil) "r")))
    printf("S9|V|%L|%L|%L|%L|%L|%L\n" cell view cv != nil
           if(cv == nil 0 length(cv~>shapes))
           if(cv == nil 0 length(cv~>instances))
           if(cv == nil 0 length(cv~>terminals)))
    when(cv != nil
      n = 0
      foreach(f cv~>shapes
        n = n + 1
        s9FigLine(f cell view n)
      )
      foreach(i cv~>instances
        printf("S9|I|%L|%L|%L|%L", cell view i~>cellName i~>name)
        s9Point(s9Get(i 'xy))
        printf("|%L|%L", s9Val(i~>transform) s9Val(s9Get(i 'justification)))
        printf("|")
        s9BBox(i)
        printf("|%L\n" length(i~>instTerms))
      )
      foreach(tm cv~>terminals
        printf("S9|T|%L|%L|%L|%L|%L|%L", cell view tm~>name tm~>direction
               if(tm~>net tm~>net~>name "NO_NET") length(tm~>pins))
        ;; every pin figure of this terminal, in one field list, is the electrical landing point
        foreach(p tm~>pins
          foreach(f p~>figs
            printf("|%L/%L/%L", f~>layerName f~>purpose f~>objType)
            printf("@")
            s9BBox(f)
          )
        )
        printf("\n")
      )
      dbClose(cv)
    )
  )
)

printf("S9-BEGIN\n")
foreach(cell s9Cells
  s9DumpView(cell "schematic")
  s9DumpView(cell "symbol")
)
printf("S9-END\n")
nil
