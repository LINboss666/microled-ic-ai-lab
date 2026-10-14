;; sc1_s3c1_probe7.il
;;
;; SCAN-1 S3C1 task 2 -- the last write-form test, and the only question left that changes the
;; plan: is direct attribute assignment a usable placement primitive in this build?
;; Measured so far: dbMoveFig returned nil in all three argument orders probed (probe6), and
;; dbCreateRect/dbCreateLine/dbCreateLabel/dbCreatePin returned nil in six forms (probe3/probe6),
;; with dbDeleteObj, geMoveFig and schCreateWire absent from the batch process. probe5/probe6
;; aborted before reaching the assignment tests, so bBox and xy are still unmeasured.
;;
;; Test object: a temporary COPY of the delivered bank symbol inside this task's own library
;; (s3c1_scratch_move:symbol). The copy IS saved on purpose -- it is a scratch cellview this task
;; created, and saving it is what proves the round trip (write -> dbSave -> reopen from disk).
;; The delivered sc1_s3b_p33_bank_7:symbol is opened read-only and the library digest list taken
;; before this run must still match afterwards for all 72 delivered files.
;; NEW_SIMULATION_RUNS = 0.

s7Lib     = "microled_scan_s3c"
s7Src     = "sc1_s3b_p33_bank_7"
s7Scratch = "s3c1_scratch_move"

s7Names = list('dbMoveFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel 'dbCreatePin 'dbDeleteObj
               'schCheck 'schCreateWire 'schDelete 'schMaintainConn 'symUpdateInst
               'schUpdateInst 'hiCheckAndSave 'hiGetSession 'hiGetEditWin 'hiCreateWindow
               'geGetEditCellView 'dbSave 'hiIssueMethod 'hiGetMenu 'symCheck)

procedure(s7Get(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s7Api(stage)
  let((n)
    foreach(n s7Names printf("S7-API %L %L %L\n" stage n getd(n)))
  )
)

procedure(s7SetBBox(obj v)
  obj~>bBox = v
)

procedure(s7SetXY(obj v)
  obj~>xy = v
)

procedure(s7ShiftBBox(f dx dy)
  let((b n1 n2)
    b = f~>bBox
    n1 = list(car(car(b)) + dx  cadr(car(b)) + dy)
    n2 = list(car(cadr(b)) + dx cadr(cadr(b)) + dy)
    s7SetBBox(f list(n1 n2))
  )
)

procedure(s7Show(f tag)
  printf("S7-FIG %L objType=%L layer=%L/%L bbox=%L xy=%L\n" tag f~>objType f~>layerName
         f~>purpose f~>bBox s7Get(f 'xy))
)

;; the three figures that make one symbol pin: pin rect (pin/drawing), stub (device/drawing),
;; name (pin/label). Their object identity is what a terminal pin refers to, so a placement
;; primitive must move all three and leave term->pins->figs pointing at the same objects.
procedure(s7PinGroup(cv tm)
  let((rect stub name)
    rect = nil
    stub = nil
    name = nil
    foreach(p tm~>pins
      foreach(f p~>figs
        when(equal(f~>layerName "pin")
          when(equal(f~>purpose "drawing") rect = f)
          when(equal(f~>purpose "label") name = f)
        )
        when(equal(f~>layerName "device") stub = f)
      )
    )
    list(rect stub name)
  )
)

printf("S7-BEGIN\n")
s7Api("START")

src = car(errset(dbOpenCellViewByType(s7Lib s7Src "symbol" nil "r")))
printf("S7-SRC %L shapes=%L terms=%L\n" src != nil if(src == nil 0 length(src~>shapes))
       if(src == nil 0 length(src~>terminals)))

scr = car(errset(dbCopyCellView(src s7Lib s7Scratch "symbol" nil)))
printf("S7-SCRATCH %L shapes=%L terms=%L\n" scr != nil if(scr == nil 0 length(scr~>shapes))
       if(scr == nil 0 length(scr~>terminals)))

when(scr
  let((g rect stub name b0 b1 r moved ch)
    ;; pick the first terminal and its pin group
    g = nil
    foreach(tm scr~>terminals
      when(g == nil g = s7PinGroup(scr tm))
    )
    rect = car(g)
    stub = cadr(g)
    name = caddr(g)
    printf("S7-GROUP rect=%L stub=%L name=%L\n" rect != nil stub != nil name != nil)
    s7Show(rect "rect-before")
    s7Show(stub "stub-before")
    s7Show(name "name-before")
    b0 = rect~>bBox

    ;; A: assign a new bBox (same size, shifted +1.0 in x) on the pin rect
    r = car(errset(s7ShiftBBox(rect 1.0 0.0)))
    b1 = rect~>bBox
    ch = if(equal(b0 b1) nil t)
    printf("S7-SETBBOX rc=%L before=%L got=%L changed=%L\n" r != nil b0 b1 ch)

    ;; B: assign xy on the label
    when(name
      let((o)
        o = name~>xy
        r = car(errset(s7SetXY(name list(car(o) + 1.0 cadr(o)))))
        printf("S7-SETXY rc=%L before=%L after=%L\n" r != nil o name~>xy)
      )
    )

    ;; C: assign bBox on the stub line
    when(stub
      let((o)
        o = stub~>bBox
        r = car(errset(s7ShiftBBox(stub 1.0 0.0)))
        printf("S7-SETBBOX-STUB rc=%L before=%L after=%L\n" r != nil o stub~>bBox)
      )
    )

    ;; does the terminal still point at the same objects after placement?
    foreach(tm scr~>terminals
      printf("S7-TERM-AFTER %L %L pins=%L\n" tm~>name tm~>direction length(tm~>pins))
      foreach(p tm~>pins
        foreach(f p~>figs s7Show(f "term-fig"))
      )
    )

    ;; persist on purpose: this is the scratch cellview, not a delivered one
    printf("S7-SAVE %L\n" car(errset(dbSave(scr))))
    printf("S7-CLOSE %L\n" car(errset(dbClose(scr))))

    ;; reopen from disk and read the geometry back
    moved = car(errset(dbOpenCellViewByType(s7Lib s7Scratch "symbol" nil "r")))
    printf("S7-REOPEN %L shapes=%L terms=%L\n" moved != nil
           if(moved == nil 0 length(moved~>shapes))
           if(moved == nil 0 length(moved~>terminals)))
    when(moved
      foreach(f moved~>shapes
        when(equal(f~>layerName "pin") s7Show(f "reopened"))
      )
      dbClose(moved)
    )
  )
)

printf("S7-TRIGGER %L\n" car(errset(dbCreateRect(scr))))
s7Api("AFTER-TRIGGER")
when(src != nil dbClose(src))
printf("S7-DONE\n")
nil
