;; sc1_s3c2_apply_sym.il
;;
;; SCAN-1 S3C2 A -- place one Symbol's pin groups to coordinates computed offline by
;; scripts/sc1_s3c2_place.py.
;;
;; Interfaces used are only ones measured working here: assigning fig~>bBox and label~>xy persists
;; through dbSave + reopen (sc1_s3c1_probe7.il, sc1_s3c2_api_probe.il) and label~>justification
;; assigns cleanly (this file: bgate reported now="centerLeft" after the write).
;;
;; How a figure is located, and why it changed once:
;;   * the pin rectangle comes from the TERMINAL itself -- cv~>terminals matching the row's name,
;;     then that terminal's pins, then their figures. No bounding-box key, so applying the same table
;;     twice gives the same picture and a half-applied view is repairable instead of orphaned;
;;   * the stub (device/drawing line) and the name (pin/label) are found on the CROSS axis of the
;;     CURRENT rectangle: a wider-than-tall box is a horizontal pin so its group shares y, otherwise
;;     the group shares x. Deriving the axis from the TARGET side was wrong and produced
;;     S2A-REFUSE for vscan (the delivered pin is still horizontal, so its stub sits at x=1.0 while
;;     the target asked for x=1.125);
;;   * pin OBJECTS and their terminal associations are never deleted or re-created, so pin, figure,
;;     stub and label move as one group as the task requires.
;;
;; Row layout: kind, cell, term/role, new rect x1 y1 x2 y2, new stub x1 y1 x2 y2, label x y,
;; justification. s3c2OnlyCell restricts the run to one cell; nil means the whole table.
;; NEW_SIMULATION_RUNS = 0.

s3c2aLib = "microled_scan_s3c"

procedure(s2aVal(v)
  if(v == nil "NONE" v)
)

procedure(s2aGet(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s2aJustSym(str)
  cond(
    (equal(str "centerRight") 'centerRight)
    (equal(str "centerLeft") 'centerLeft)
    (equal(str "lowCenter") 'lowCenter)
    (equal(str "topCenter") 'topCenter)
    (t nil)
  )
)

procedure(s2aSetBBox(f b)
  f~>bBox = b
)

procedure(s2aSetXY(f p)
  f~>xy = p
)

procedure(s2aSetJust(f j)
  f~>justification = j
)

procedure(s2aBx(b)
  ((car(car(b)) + car(cadr(b))) / 2.0)
)

procedure(s2aBy(b)
  ((cadr(car(b)) + cadr(cadr(b))) / 2.0)
)

procedure(s2aWidth(b)
  (car(cadr(b)) - car(car(b)))
)

procedure(s2aHeight(b)
  (cadr(cadr(b)) - cadr(car(b)))
)

;; the terminal's own pin figure, on the pin/drawing layer
procedure(s2aPinRect(cv, termName)
  let((hit count)
    hit = nil
    count = 0
    foreach(tm cv~>terminals
      when(equal(tm~>name termName)
        foreach(p tm~>pins
          foreach(f p~>figs
            when(equal(f~>layerName "pin")
              when(equal(f~>purpose "drawing")
                hit = f
                count = count + 1
              )
            )
          )
        )
      )
    )
    when(count != 1 printf("S2A-REFUSE %L terminal pin figure count=%L\n" termName count))
    list(count hit)
  )
)

procedure(s2aFindAxis(cv, what, lyr, pur, want, axis)
  let((hit count)
    hit = nil
    count = 0
    foreach(f cv~>shapes
      when(equal(f~>objType what)
        when(equal(f~>layerName lyr)
          when(equal(f~>purpose pur)
            let((d b)
              b = f~>bBox
              when(b != nil
                d = nil
                when(equal(axis "y") d = s2aBy(b))
                when(equal(axis "x") d = s2aBx(b))
                when(d != nil
                  when(abs(d - want) < 0.02
                    hit = f
                    count = count + 1
                  )
                )
              )
            )
          )
        )
      )
    )
    list(count hit)
  )
)

procedure(s2aFindLayer(cv, lyr)
  let((hit count)
    hit = nil
    count = 0
    foreach(f cv~>shapes
      when(equal(f~>objType "rect")
        when(equal(f~>layerName lyr)
          when(equal(f~>purpose "drawing")
            hit = f
            count = count + 1
          )
        )
      )
    )
    when(count != 1 printf("S2A-REFUSE body %L count=%L\n" lyr count))
    list(count hit)
  )
)

;; Row fields (all of scripts/sc1_s3c2_place.py's plan columns, unchanged):
;;   0 kind, 1 cell, 2 term or body role,
;;   3..6 the ORIGINAL rectangle box -- the only key used to find this pin's stub and name,
;;   7..10 the TARGET rectangle box (for a body row, the target body / selection box),
;;   11..14 the target stub box, 15..16 the target name anchor, 17 the target justification.
;; Keying the group on the ORIGINAL box matters: once a rectangle has moved, keying on its current
;; centre hands the neighbouring pin's stub to this row (measured in the run before this comment).
procedure(s2aRow(cv, row)
  let((cell term k1 k2 k3 k4 new1 new2 new3 new4 rc rect axis want stub lab j)
    cell = nth(1 row)
    term = nth(2 row)
    k1 = nth(3 row)
    k2 = nth(4 row)
    k3 = nth(5 row)
    k4 = nth(6 row)
    new1 = nth(7 row)
    new2 = nth(8 row)
    new3 = nth(9 row)
    new4 = nth(10 row)
    ;; the delivered pin is horizontal so its group shares a y; a vertical one would share an x
    axis = "y"
    when((k3 - k1) < (k4 - k2) axis = "x")
    want = (k2 + k4) / 2.0
    when(equal(axis "x") want = (k1 + k3) / 2.0)
    when(equal(nth(0 row) "body")
      rc = s2aFindLayer(cv term)
      when(nth(0 rc) == 1
        s2aSetBBox(nth(1 rc) list(list(new1 new2) list(new3 new4)))
        printf("S2A-BODY %L %L after=%L\n" cell term nth(1 rc)~>bBox)
      )
    )
    when(equal(nth(0 row) "pin")
      rc = s2aPinRect(cv term)
      rect = nth(1 rc)
      when(rect == nil
        printf("S2A-REFUSE %L %L no unique terminal pin figure\n" cell term)
      )
      when(rect != nil
        s2aSetBBox(rect list(list(new1 new2) list(new3 new4)))
        rc = s2aFindAxis(cv "line" "device" "drawing" want axis)
        stub = nth(1 rc)
        ;; A line is NOT relocated by assigning its bBox (measured: bgate came back mirrored onto
        ;; the right and scan kept its old y). The stub is a cosmetic device/drawing figure -- the
        ;; electrical pin is the pin/drawing rectangle -- so the new stub is CREATED first and the
        ;; old one deleted afterwards: the pin is never left without its drawing.
        when(stub != nil
          let((nl)
            nl = car(errset(dbCreateLine(cv list("device" "drawing")
                                         list(list(nth(11 row) nth(12 row))
                                             list(nth(13 row) nth(14 row))))))
            printf("S2A-STUB-NEW %L %L rc=%L bbox=%L shapes=%L\n" cell term nl != nil
                   if(nl == nil nil nl~>bBox) length(cv~>shapes))
            when(nl != nil
              printf("S2A-STUB-OLD-GONE %L %L rc=%L shapes=%L\n" cell term
                     car(errset(dbDeleteObject(stub))) != nil length(cv~>shapes))
            )
          )
        )
        when(stub == nil
          printf("S2A-NOSTUB %L %L count=%L want=%L axis=%L\n" cell term nth(0 rc) want axis)
        )
        rc = s2aFindAxis(cv "label" "pin" "label" want axis)
        lab = nth(1 rc)
        when(lab != nil
          let((bb)
            bb = lab~>bBox
            s2aSetXY(lab list(nth(15 row) nth(16 row)))
            j = s2aJustSym(nth(17 row))
            when(j != nil
              let((was)
                was = s2aGet(lab 'justification)
                s2aSetJust(lab j)
                printf("S2A-JUST %L %L want=%L was=%L now=%L\n" cell term j was
                       s2aGet(lab 'justification))
              )
            )
            printf("S2A-LABEL %L %L before=%L after=%L xy=%L now=%L\n" cell term bb lab~>bBox
                   lab~>xy s2aVal(s2aGet(lab 'justification)))
          )
        )
        when(lab == nil
          printf("S2A-REFUSE %L %L label count=%L want=%L axis=%L\n" cell term nth(0 rc) want axis)
        )
        printf("S2A-PIN %L %L axis=%L newTip=%L %L stub=%L label=%L\n" cell term axis
               (new1 + new3) / 2.0 (new2 + new4) / 2.0 stub != nil lab != nil)
      )
    )
  )
)

procedure(s3c2Include(c)
  if(s3c2OnlyCell == nil t equal(c s3c2OnlyCell))
)

procedure(s2aApply(rows)
  let((cells cv c n)
    cells = nil
    foreach(row rows
      c = nth(1 row)
      when(s3c2Include(c)
        when(member(c cells) == nil cells = cons(c cells))
      )
    )
    printf("S3C2A-CELLS-TO-WRITE %L %L\n" length(cells) cells)
    foreach(c cells
      cv = car(errset(dbOpenCellViewByType(s3c2aLib c "symbol" nil "a")))
      printf("S2A-OPEN %L %L shapes=%L terms=%L\n" c cv != nil
             if(cv == nil 0 length(cv~>shapes)) if(cv == nil 0 length(cv~>terminals)))
      when(cv != nil
        n = 0
        foreach(row rows
          when(equal(nth(1 row) c)
            s2aRow(cv row)
            n = n + 1
          )
        )
        printf("S2A-ROWS-DONE %L %L\n" c n)
        printf("S2A-SAVE %L %L\n" c car(errset(dbSave(cv))) != nil)
        dbClose(cv)
      )
    )
    printf("S3C2A-DONE\n")
  )
)

nil
