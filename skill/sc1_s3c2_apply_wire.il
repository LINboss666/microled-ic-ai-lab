;; sc1_s3c2_apply_wire.il
;;
;; SCAN-1 S3C2 C -- apply the parent re-lay: move the blocks and the ports to their planned
;; positions, delete the target view's wire figures, then redraw one figure per planned segment and
;; give it the net object the database reports for that name. Every write uses the argument form
;; section 3 of the task book documents and sc1_s3c2_api_probe.il measured on this build:
;;   dbCreateLine(cellView lpp list(list(x1 y1) list(x2 y2)))
;;   dbDeleteObject(fig)
;;   fig~>net = netObj
;;   obj~>xy = list(x y)
;;
;; Fail-closed by construction:
;;   * if any planned move does not take, the view's wires are NOT touched at all and the cell is
;;     reported SKIP-AFTER-MOVE-FAILURE -- a drawing that assumes moved pins would be a lie;
;;   * a segment whose net name is not a net of this view is refused (NO-SUCH-NET) rather than drawn
;;     unattached, so the graphics always come from a real connection;
;;   * the editor's own check runs after the redraw and before the save, and its error/warning
;;     counts are printed as numbers (nil is printed as NONE and never read as zero);
;;   * every phase prints counts before and after, so a silent no-op cannot look like success.
;;
;; NEW_SIMULATION_RUNS = 0. Only microled_scan_s3c is written.

procedure(s2wGet(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s2wVal(v)
  if(v == nil "NONE" v)
)

;; planned coordinates arrive as numbers already; float() keeps a string coordinate usable
procedure(s2wNum(v)
  let((r)
    r = car(errset(float(v)))
    if(r == nil v r)
  )
)

procedure(s2wSetXY(obj pt)
  obj~>xy = pt
)

procedure(s2wSetNet(obj net)
  obj~>net = net
)

procedure(s2wFindNet(cv name)
  let((out)
    out = nil
    foreach(n cv~>nets
      when(out == nil
        when(equal(s2wVal(n~>name) name) out = n)
      )
    )
    out
  )
)

procedure(s2wFindInst(cv name)
  let((out)
    out = nil
    foreach(i cv~>instances
      when(out == nil
        when(equal(s2wVal(i~>name) name) out = i)
      )
    )
    out
  )
)

;; a port's name display is a separate shape; it is identified by its exact current anchor. The
;; objType/layer are NOT tested here: the dump's %L cannot tell a string attribute from a symbol one
;; (measured in S3C1), and a wrong guess would silently skip every text move. Comparison is by
;; equal(), not by an arithmetic tolerance, because these anchors are multiples of 1/32 and SKILL
;; has no infix subtraction -- an expression like abs(a - b) is a call with three arguments.
procedure(s2wFindText(cv x y)
  let((out p)
    out = nil
    p = nil
    foreach(f cv~>shapes
      when(out == nil
        p = s2wGet(f 'xy)
        when(p != nil
          when(equal(car(p) x)
            when(equal(cadr(p) y)
              out = f
            )
          )
        )
      )
    )
    out
  )
)

procedure(s2wProbeShapes(cv cell)
  let((n p)
    n = 0
    p = nil
    foreach(f cv~>shapes
      n = n + 1
      p = s2wGet(f 'xy)
      printf("S2W-SHAPE %L %L objType=%L lpp=%L/%L xy=%L text=%L strings=%L val=%L\n"
             cell n f~>objType s2wVal(f~>layerName) s2wVal(f~>purpose) s2wVal(p)
             s2wVal(s2wGet(f 'text)) s2wVal(s2wGet(f 'strings)) s2wVal(s2wGet(f 'val)))
    )
    printf("S2W-SHAPES %L count=%L\n" cell n)
  )
)

procedure(s2wApplyMove(cv row)
  let((cell kind x y obj r was ox oy)
    cell = nth(0 row)
    kind = nth(1 row)
    r = nil
    obj = nil
    when(equal(kind "inst")
      obj = s2wFindInst(cv nth(2 row))
      when(obj == nil
        printf("S2W-MOVE-MISSING-INST %L %L\n" cell nth(2 row))
      )
      when(obj != nil
        x = s2wNum(nth(3 row))
        y = s2wNum(nth(4 row))
        was = s2wGet(obj 'bBox)
        r = car(errset(s2wSetXY(obj list(x y))))
        when(r == nil
          r = car(errset(dbMoveFig(obj cv list(list(x y) "R0" 1.0))))
        )
        printf("S2W-MOVE-INST %L want=%L xy=%L rc=%L bbox-was=%L bbox-now=%L\n" nth(2 row)
               list(x y) s2wVal(s2wGet(obj 'xy)) r != nil was s2wGet(obj 'bBox))
      )
    )
    when(equal(kind "text")
      ox = s2wNum(nth(2 row))
      oy = s2wNum(nth(3 row))
      obj = s2wFindText(cv ox oy)
      when(obj == nil
        printf("S2W-MOVE-MISSING-TEXT %L want-xy=(%L %L) got=%L %L\n" cell ox oy
               s2wNum(nth(4 row)) s2wNum(nth(5 row)))
      )
      when(obj != nil
        x = s2wNum(nth(4 row))
        y = s2wNum(nth(5 row))
        r = car(errset(s2wSetXY(obj list(x y))))
        printf("S2W-MOVE-TEXT (%L %L) -> (%L %L) rc=%L now=%L\n" ox oy x y r != nil
               s2wVal(s2wGet(obj 'xy)))
      )
    )
    r != nil
  )
)

procedure(s2wKept(cell net)
  let((out)
    out = nil
    foreach(k s2wKeep
      when(out == nil
        when(equal(nth(0 k) cell)
          when(equal(nth(1 k) net) out = t)
        )
      )
    )
    out
  )
)

procedure(s2wWireFigures(cv cell)
  let((out)
    out = nil
    foreach(f cv~>shapes
      when(equal(f~>layerName "wire")
        ;; a net listed in s2wKeep had no crossing-free replacement route: its existing figures
        ;; stay exactly as they are instead of being deleted and stubbed
        when(s2wKept(cell s2wVal(if(f~>net f~>net~>name nil))) == nil
          out = cons(f out)
        )
      )
    )
    out
  )
)

procedure(s2wDrawRow(cv row)
  let((cell net x1 y1 x2 y2 fig nobj)
    cell = nth(0 row)
    net = nth(1 row)
    x1 = s2wNum(nth(2 row))
    y1 = s2wNum(nth(3 row))
    x2 = s2wNum(nth(4 row))
    y2 = s2wNum(nth(5 row))
    fig = nil
    nobj = s2wFindNet(cv net)
    when(nobj == nil
      printf("S2W-NO-SUCH-NET %L %L\n" cell net)
    )
    when(nobj != nil
      fig = car(errset(dbCreateLine(cv list("wire" "drawing")
                                    list(list(x1 y1) list(x2 y2)))))
      when(fig == nil
        printf("S2W-CREATE-FAILED %L %L (%L %L)->(%L %L)\n" cell net x1 y1 x2 y2)
      )
      when(fig != nil
        when(car(errset(s2wSetNet(fig nobj))) == nil
          printf("S2W-SETNET-FAILED %L %L\n" cell net)
        )
        printf("S2W-SEG %L %L (%L %L)->(%L %L) objType=%L net=%L\n" cell net x1 y1 x2 y2
               fig~>objType s2wVal(if(fig~>net fig~>net~>name nil)))
      )
    )
    fig
  )
)

procedure(s2wDrawLabel(cv row)
  let((cell net x y text just lab)
    cell = nth(0 row)
    net = nth(1 row)
    x = s2wNum(nth(2 row))
    y = s2wNum(nth(3 row))
    text = nth(4 row)
    just = nth(5 row)
    lab = car(errset(dbCreateLabel(cv list("wire" "label") list(x y) text just "R0" "stick"
                                   0.0625)))
    when(lab == nil
      printf("S2W-LABEL-FAILED %L %L %L\n" cell net text)
    )
    when(lab != nil
      printf("S2W-LABEL %L %L at (%L %L) text=%L strings=%L val=%L just=%L objType=%L\n" cell net
             x y s2wVal(s2wGet(lab 'text)) s2wVal(s2wGet(lab 'strings))
             s2wVal(s2wGet(lab 'val)) s2wVal(s2wGet(lab 'justification)) s2wVal(lab~>objType))
    )
    lab
  )
)

procedure(s2wRowsFor(cell rows)
  let((out)
    out = nil
    foreach(r rows
      when(equal(nth(0 r) cell) out = cons(r out))
    )
    reverse(out)
  )
)

procedure(s2wApplyCell(cell)
  let((cv before moved moves_failed deleted created labelled res errs warns ok)
    cv = car(errset(dbOpenCellViewByType(s2wLib cell "schematic" "schematic" "a")))
    when(cv == nil
      printf("S2W-OPEN-FAILED %L\n" cell)
    )
    when(cv != nil
      before = length(cv~>shapes)
      s2wProbeShapes(cv cell)
      moved = 0
      moves_failed = 0
      foreach(r s2wRowsFor(cell s2wMoves)
        ok = s2wApplyMove(cv r)
        if(ok == nil moves_failed = moves_failed + 1 moved = moved + 1)
      )
      printf("S2W-MOVES %L applied=%L refused=%L shapes=%L\n" cell moved moves_failed before)
      when(moves_failed == 0
        let((n old)
          ;; the figures that exist now are remembered, the new ones are drawn while the old ones
          ;; are still present, and only then are the old ones deleted. Order matters: deleting a
          ;; net's last figure first makes Virtuoso rename the net (measured in the S3C2 loop test,
          ;; where the internal gate33 net came back as net11), and a re-lay must not rename a net.
          old = s2wWireFigures(cv cell)
          created = 0
          foreach(r s2wRowsFor(cell s2wRows)
            when(s2wDrawRow(cv r) != nil created = created + 1)
          )
          n = 0
          foreach(f old
            when(car(errset(dbDeleteObject(f))) != nil n = n + 1)
          )
          deleted = n
          printf("S2W-DELETE %L wire-figures-deleted=%L shapes=%L->%L\n" cell deleted before
                 length(cv~>shapes))
          labelled = 0
          foreach(r s2wRowsFor(cell s2wLabels)
            when(s2wDrawLabel(cv r) != nil labelled = labelled + 1)
          )
          res = errset(schCheck(cv))
          printf("S2W-SCHCHECK %L raw=%L\n" cell s2wVal(res))
          when(car(res) != nil
            errs = car(car(res))
            warns = cadr(car(res))
          )
          printf("S2W-DRAW %L segments=%L labels=%L shapes=%L->%L errors=%L warnings=%L\n" cell
                 created labelled before length(cv~>shapes) s2wVal(errs) s2wVal(warns))
          printf("S2W-SAVE %L rc=%L\n" cell car(errset(dbSave(cv))) != nil)
        )
      )
      when(moves_failed != 0
        printf("S2W-SKIP-AFTER-MOVE-FAILURE %L\n" cell)
      )
      printf("S2W-CLOSE %L rc=%L\n" cell car(errset(dbClose(cv))) != nil)
    )
  )
)

;; ---- TABLES ----
;; the generator (scripts/sc1_s3c2_route.py --applier) splices the copy step and the s2wRows /
;; s2wLabels / s2wMoves tables in here, so exactly ONE file is loaded: a nested load in this build
;; leaves the inner file's procedures unbound at the call site (measured in S3C1).

printf("S2W-BEGIN\n")
printf("S2W-API dbCreateLine=%L dbDeleteObject=%L dbCreateLabel=%L dbMoveFig=%L schCheck=%L\n"
       getd('dbCreateLine) getd('dbDeleteObject) getd('dbCreateLabel) getd('dbMoveFig)
       getd('schCheck))
s2wCells = nil
foreach(r s2wRows
  when(car(errset(member(nth(0 r) s2wCells))) == nil
    s2wCells = cons(nth(0 r) s2wCells)
  )
)
s2wCells = reverse(s2wCells)
printf("S2W-CELLS %L rows=%L labels=%L moves=%L\n" s2wCells length(s2wRows) length(s2wLabels)
       length(s2wMoves))
foreach(c s2wCells s2wApplyCell(c))
printf("S2W-DONE\n")
nil
