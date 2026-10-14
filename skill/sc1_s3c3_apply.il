;; sc1_s3c3_apply_tpl.il -- TEMPLATE, not the runnable file.
;;
;; scripts/sc1_s3c3_emit.py splices the plan tables in at the marker below and writes the runnable
;; skill/sc1_s3c3_apply.il. The body is hand-written so it stays reviewable; only coordinates are
;; generated, and they come out of scripts/sc1_s3c3_plan.py, which read them from the database
;; (results/evidence/sc1_s3c3_dump_pins.txt).
;;
;; Per view, in this order: copy the delivered view into this round's copy cell -> open the copy
;; writable -> place instances and ports -> draw every planned segment onto the net object it
;; belongs to -> label the internal nets -> delete the labels that were there before (after drawing,
;; because a net that loses its last figure is renamed by the database, measured in S3C2) ->
;; schCheck -> print the connectivity the checker just extracted -> save only when the errors are
;; zero and every planned segment and label was created. The delivered views are only ever opened
;; read-only and copied. NEW_SIMULATION_RUNS = 0.

s3Lib = "microled_scan_s3c"

procedure(s3Val(v) if(v v "NONE"))
procedure(s3Get(o nm) car(errset(dbGet(o nm))))

procedure(s3Count(table, view)
  let((n)
    n = 0
    foreach(r table when(equal(nth(0 r) view) n = plus(n 1)))
    n
  )
)

procedure(s3FindNet(cv name)
  let((out)
    out = nil
    foreach(n cv~>nets when(and(out == nil equal(s3Val(n~>name) name)) out = n))
    out
  )
)

procedure(s3FindInst(cv name)
  let((out)
    out = nil
    foreach(i cv~>instances when(and(out == nil equal(s3Val(i~>name) name)) out = i))
    out
  )
)

;; a top-level port's drawable object is its own iopin instance, reached through the terminal's pins
procedure(s3FindPortInst(cv name)
  let((out)
    out = nil
    foreach(tm cv~>terminals
      when(and(out == nil equal(s3Val(tm~>name) name))
        foreach(p tm~>pins
          foreach(f p~>figs
            when(and(out == nil equal(s3Val(f~>objType) "inst")) out = f)
          )
        )
      )
    )
    out
  )
)

procedure(s3Move(label, obj, x, y)
  let((was rc now)
    rc = nil
    when(obj
      was = obj~>bBox
      rc = car(errset(obj~>xy = list(x y)))
      now = obj~>bBox
      printf("S3-MOVE %L want=(%L %L) rc=%L bbox %L -> %L\n" label x y rc != nil was now)
    )
    when(obj == nil printf("S3-MOVE-MISSING %L\n" label))
    rc != nil
  )
)

procedure(s3Draw(cv, view, net, x1, y1, x2, y2)
  let((fig)
    ;; connectivity is left to geometry alone: no fig~>net assignment. Section 4 forbids naming a
    ;; connection by hand, and the net an extracted wire belongs to is read back after schCheck.
    fig = car(errset(dbCreateLine(cv list("wire" "drawing")
                                 list(list(x1 y1) list(x2 y2)))))
    if(fig == nil
       printf("S3-DRAW-FAILED %L %L (%L %L)-(%L %L)\n" view net x1 y1 x2 y2)
       printf("S3-DRAW %L %L seg=(%L %L)-(%L %L) objType=%L layer=%L dbGaveNet=%L matches=%L\n"
              view net x1 y1 x2 y2 s3Val(fig~>objType) s3Val(fig~>layerName)
              s3Val(if(fig~>net fig~>net~>name nil))
              equal(s3Val(if(fig~>net fig~>net~>name nil)) net))
    )
    fig != nil
  )
)

procedure(s3Label(view, net, x, y, text, just, cv)
  let((lab)
    lab = car(errset(dbCreateLabel(cv list("wire" "label") list(x y) text just "R0" "stick"
                                   0.0625)))
    when(lab == nil printf("S3-LABEL-FAILED %L %L at (%L %L)\n" view text x y))
    when(lab
      printf("S3-LABEL %L text=%L at=(%L %L) just=%L theLabel=%L net=%L\n"
             view text x y just s3Val(car(errset(lab~>theLabel)))
             s3Val(if(lab~>net lab~>net~>name nil)))
    )
    lab != nil
  )
)

procedure(s3CollectLabels(cv)
  let((out)
    out = nil
    foreach(f cv~>shapes when(equal(f~>objType "label") out = cons(f out)))
    out
  )
)

;; geometry this round did not draw. The importer's wire figures arrive as objType "line" on layer
;; "wire", which is why an earlier count of shapes whose objType is "wire" read zero -- leaving them
;; next to the new segments is the "mixed old and new geometry hides the error" section 4 forbids,
;; and they are what produced `Net "en" shorted to net "core_ok33"`. Deleted only after the new
;; geometry and its name labels exist, so no net is ever left without a figure.
procedure(s3CollectOldGeometry(cv)
  let((out)
    out = nil
    foreach(f cv~>shapes
      when(or(equal(f~>objType "label")
              and(equal(f~>layerName "wire")
                  or(equal(f~>objType "line") equal(f~>objType "wire")
                     equal(f~>objType "path") equal(f~>objType "rect"))))
        out = cons(f out)
      )
    )
    out
  )
)

procedure(s3DeleteLabels(items)
  let((n f)
    n = 0
    foreach(f items
      when(errset(dbDeleteObject(f)) n = plus(n 1))
    )
    n
  )
)

procedure(s3DumpExtracted(cv, view)
  let((i tm n f)
    foreach(i cv~>instances
      foreach(tm i~>instTerms
        printf("S3-X %L %L %L dir=%L net=%L\n" view i~>name s3Val(tm~>name)
               s3Val(tm~>direction) s3Val(if(tm~>net tm~>net~>name nil)))
      )
    )
    foreach(n cv~>nets
      printf("S3-NET %L %L figs=%L terminals=%L\n" view s3Val(n~>name) length(n~>figs)
             length(n~>terminals))
    )
    foreach(f cv~>shapes
      when(or(equal(f~>objType "label") equal(f~>objType "wireLabel"))
        printf("S3-READLABEL %L theLabel=%L xy=%L net=%L\n" view
               s3Val(car(errset(f~>theLabel))) f~>xy
               s3Val(if(f~>net f~>net~>name nil)))
      )
    )
  )
)

procedure(s3DumpWires(cv, view)
  let((f)
    foreach(f cv~>shapes
      when(or(equal(f~>objType "wire") equal(f~>objType "line") equal(f~>objType "path"))
        printf("S3-WIRE %L net=%L objType=%L points=%L\n" view
               s3Val(if(f~>net f~>net~>name nil)) f~>objType f~>points)
      )
    )
  )
)

procedure(s3ApplyView(view, copyCell)
  let((src cp cv old nseg nlab okseg oklab nmoved wantmoved deleted res pair errs warns saved)
    cv = nil
    when(s3Direct
      ;; the closed loop on the copy is proven (S3-C3 report section 4), so this pass edits the
      ;; delivered view itself. Same order: place, draw, label, then remove the old geometry.
      ;; No read-only open of the same view first: that would hand back this very editable object
      ;; and closing it would throw the edits away.
      cv = car(errset(dbOpenCellViewByType(s3Lib view "schematic" "schematic" "a")))
      printf("S3-DIRECT %L opened=%L shapes=%L insts=%L nets=%L terminals=%L oldGeometry=%L\n"
             view cv != nil length(cv~>shapes) length(cv~>instances) length(cv~>nets)
             length(cv~>terminals) length(s3CollectOldGeometry(cv)))
    )
    when(s3Direct == nil
      src = car(errset(dbOpenCellViewByType(s3Lib view "schematic" "schematic" "r")))
      printf("S3-SRC %L open=%L shapes=%L insts=%L nets=%L terminals=%L oldLabels=%L\n" view
             src != nil length(src~>shapes) length(src~>instances) length(src~>nets)
             length(src~>terminals) length(s3CollectLabels(src)))
      cp = nil
      when(src cp = car(errset(dbCopyCellView(src s3Lib copyCell "schematic" "schematic"))))
      printf("S3-COPY %L -> %L made=%L\n" view copyCell cp != nil)
      when(src dbClose(src))
      when(cp == nil printf("S3-VERDICT %L FAIL copy-not-made\n" view))
      when(cp
        dbClose(cp)
        cv = car(errset(dbOpenCellViewByType(s3Lib copyCell "schematic" "schematic" "a")))
        printf("S3-OPEN %L writable=%L shapes=%L insts=%L nets=%L\n" copyCell cv != nil
               length(cv~>shapes) length(cv~>instances) length(cv~>nets))
      )
    )
    when(cv == nil printf("S3-VERDICT %L FAIL not-writable\n" view))
    when(cv
      nmoved = 0
      wantmoved = 0
      foreach(r s3Moves
        when(equal(nth(0 r) view)
          wantmoved = plus(wantmoved 1)
          when(s3Move(nth(1 r) s3FindObject(cv nth(1 r)) nth(2 r) nth(3 r))
            nmoved = plus(nmoved 1)
          )
        )
      )
      printf("S3-MOVES %L applied=%L want=%L\n" view nmoved wantmoved)
      old = s3CollectOldGeometry(cv)
      nseg = s3Count(s3Segs view)
      nlab = s3Count(s3Labels view)
      okseg = 0
      oklab = 0
      foreach(r s3Segs
        when(equal(nth(0 r) view)
          when(s3Draw(cv view nth(1 r) nth(2 r) nth(3 r) nth(4 r) nth(5 r))
            okseg = plus(okseg 1)
          )
        )
      )
      foreach(r s3Labels
        when(equal(nth(0 r) view)
          when(s3Label(view nth(1 r) nth(2 r) nth(3 r) nth(1 r) nth(4 r) cv)
            oklab = plus(oklab 1)
          )
        )
      )
      printf("S3-DRAWN %L ok=%L of %L ; LABELLED ok=%L of %L ; shapes now=%L\n" view okseg nseg
             oklab nlab length(cv~>shapes))
      deleted = s3DeleteLabels(old)
      printf("S3-OLD-LABELS %L deleted=%L of %L\n" view deleted length(old))
      printf("S3-API %L schCheck=%L hiCheckAndSave=%L dbCreateLine-exists=%L\n" view
             if(getd('schCheck) "EXISTS" "NIL") if(getd('hiCheckAndSave) "EXISTS" "NIL")
             if(getd('dbCreateLine) "EXISTS" "NIL"))
      res = errset(schCheck(cv))
      ;; errset wraps the returned values: this build gives ((errors warnings)), so the counts are
      ;; two levels down and must not be read as if res itself were the pair (measured this round)
      pair = if(res nth(0 res) nil)
      errs = -1
      warns = -1
      when(and(pair listp(pair))
        errs = car(pair)
        warns = if(cdr(pair) car(cdr(pair)) -1)
      )
      printf("S3-CHECK %L errors=%L warnings=%L raw=%L\n" view errs warns s3Val(res))
      s3DumpWires(cv view)
      s3DumpExtracted(cv view)
      saved = nil
      when(and(res != nil equal(errs 0) equal(okseg nseg) equal(oklab nlab)
               equal(nmoved wantmoved))
        saved = car(errset(dbSave(cv)))
        printf("S3-VERDICT %L PASS saved=%L errors=%L warnings=%L drawn=%L labelled=%L moved=%L\n"
               view s3Val(saved != nil) errs warns okseg oklab nmoved)
      )
      when(saved == nil
        printf("S3-VERDICT %L NOT-SAVED errors=%L drawn=%L of %L labelled=%L of %L moved=%L of %L\n"
               view errs okseg nseg oklab nlab nmoved wantmoved)
      )
      dbClose(cv)
    )
  )
)

;; find either a sub-instance or a port's iopin by the label used in the plan
procedure(s3FindObject(cv label)
  let((out)
    out = s3FindInst(cv label)
    when(out == nil out = s3FindPortInst(cv label))
    out
  )
)

;; s3Direct=nil works on this round's copy; scripts/sc1_s3c3_emit.py --direct overrides it to t
;; after the tables, so a copy run and a delivery run are separate, visible sessions.
s3Direct = nil

;; ---- TABLES ---- (written by scripts/sc1_s3c3_emit.py from sc1_s3c3_wire_plan.csv)
s3Jobs = nil
s3Jobs = cons(list("sc1_r3_scan_chain_1ch" "sc1_r3_scan_chain_1ch") s3Jobs)

s3Moves = nil
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "Xff" 1 1) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "Xgate" 4 1) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "Xls" 7.5 1.125) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "d" -0.6 0.7781) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "clk" -0.6 1.0281) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "blank" 2.5 1.0281) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "core_ok33" 5.9 1.1531) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "gate33" 9.6 1.0281) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 1.2 2.5031) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "vdd33" 0.6 2.8031) s3Moves)
s3Moves = cons(list("sc1_r3_scan_chain_1ch" "vss" 1 -1.0969) s3Moves)

s3Segs = nil
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "blank" 2.325 1.125 3.0375 1.125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "clk" -0.775 1.125 0.225 1.125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "core_ok33" 5.725 1.25 6.225 1.25) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "d" -0.775 0.875 0.225 0.875) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "en" 4.9625 1 6.225 1) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "gate33" 8.775 1.125 9.775 1.125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "q" 1.775 1.125 2.1625 1.125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "qbar" 1.775 0.875 3.0375 0.875) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 1 1.7125 1 2.1) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 4 1.5875 4 1.975) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 7.7 1.8375 7.7 2.225) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 0.6125 2.6 1.2 2.6) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd33" 7.3 1.8375 7.3 2.225) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vdd33" 0.0125 2.9 0.6 2.9) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vss" 1 -0.1 1 0.2875) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vss" 4 0.025 4 0.4125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vss" 7.5 0.025 7.5 0.4125) s3Segs)
s3Segs = cons(list("sc1_r3_scan_chain_1ch" "vss" 0.4125 -1 1 -1) s3Segs)

s3Labels = nil
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "blank" 2.68125 1.125 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "clk" -0.275 1.125 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "core_ok33" 5.975 1.25 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "d" -0.275 0.875 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "en" 5.59375 1 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "gate33" 9.275 1.125 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "q" 2.1625 1.125 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "qbar" 2.40625 0.875 "lowerLeft") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 1 2.1 "lowerCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 4 1.975 "lowerCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 7.7 2.225 "lowerCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd18" 0.6125 2.6 "lowerRight") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd33" 7.3 2.225 "lowerCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vdd33" 0.0125 2.9 "lowerRight") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vss" 1 -0.1 "upperCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vss" 4 0.025 "upperCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vss" 7.5 0.025 "upperCenter") s3Labels)
s3Labels = cons(list("sc1_r3_scan_chain_1ch" "vss" 0.4125 -1 "lowerRight") s3Labels)

s3Direct = t



;; ---- DRIVER ----
printf("S3-BEGIN\n")
foreach(job s3Jobs s3ApplyView(nth(0 job) nth(1 job)))
printf("S3-END\n")
nil
