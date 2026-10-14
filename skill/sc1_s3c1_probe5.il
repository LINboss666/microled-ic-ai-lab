;; sc1_s3c1_probe5.il
;;
;; SCAN-1 S3C1 task 2, attempt 3 (the last allowed by "同一具体问题最多三次修复尝试").
;; probe4 produced three measurements that change the code, and this file tests the corrected
;; forms:
;;   M1  objType and purpose come back as STRINGS, not symbols ("line"/"drawing" with
;;       type=string), so every earlier  f~>objType == 'rect  comparison was false without
;;       raising. That, not a missing figure, is why probe3's pin filter counted 0.
;;   M2  dbMoveFig(fig, delta) is wrong: a bare call raised
;;       "*Error* dbMoveFig: Invalid cellView - (-0.125 0.0)", i.e. the first argument must be a
;;       cellView. Forms tried here: (cellView fig delta) and (cellView list(fig) delta).
;;   M3  labels expose an xy attribute (probe4: label xy=(2.6875 0.1875)) while rects report
;;       xy=nil, so a label may be placed by assigning xy and a box figure by assigning bBox.
;;       Every write is attempted through a helper procedure so errset catches a raise and the
;;       file keeps going -- an earlier version lost the rest of its results to one bare raise.
;;   M4  string equality itself is checked (equal vs ==) because the filters depend on it.
;;
;; Target is s3c_asg_shell:schematic, the helper cell this task created in S3-C (18 shapes =
;; 9 wire lines + 9 labels, 0 terminals, 1 instance). It is NOT one of the eight delivered cells.
;; Nothing is dbSave'd and every change is reversed before closing; the delivered bank symbol is
;; opened read-only, only to confirm the same string objType/purpose on its pin rectangles.
;; NEW_SIMULATION_RUNS = 0.

s5Lib   = "microled_scan_s3c"
s5Shell = "s3c_asg_shell"
s5Sym   = "sc1_s3b_p33_bank_7"

s5Names = list('dbMoveFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel 'dbCreatePin
               'dbCreateFig 'dbDeleteObj 'schCheck 'schCreateWire 'schDelete 'schMaintainConn
               'symUpdateInst 'schUpdateInst 'hiCheckAndSave 'hiGetSession 'hiGetEditWin
               'geGetEditCellView 'dbSave 'geMoveFig 'hiIssueMethod 'hiGetConfig)

procedure(s5Get(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s5Api(stage)
  let((n)
    foreach(n s5Names printf("S5-API %L %L %L\n" stage n getd(n)))
  )
)

;; M4: does a string figure attribute match with equal, or with == ?
procedure(s5Cmp(val nm)
  let((a b)
    a = equal(val nm)
    b = nil
    b = val == nm
    printf("S5-CMP want=%L val=%L equal=%L ste=%L\n" nm val a b)
    a
  )
)

procedure(s5IsStr(val nm)
  equal(val nm)
)

;; helpers so a raise is caught by errset instead of aborting the load
procedure(s5SetBBox(obj v)
  obj~>bBox = v
)

procedure(s5SetXY(obj v)
  obj~>xy = v
)

procedure(s5Move3(cv f d)
  dbMoveFig(cv f d)
)

procedure(s5Move3L(cv fs d)
  dbMoveFig(cv fs d)
)

procedure(s5Rect3(cv lpp pts)
  dbCreateRect(cv lpp pts)
)

procedure(s5Rect4(cv lyr pur pts)
  dbCreateRect(cv lyr pur pts)
)

procedure(s5Line3(cv lpp pts)
  dbCreateLine(cv lpp pts)
)

procedure(s5Label3(cv lpp pt txt)
  dbCreateLabel(cv lpp pt txt)
)

procedure(s5Pin3(cv lpp pts)
  dbCreatePin(cv lpp pts)
)

procedure(s5Show(f tag)
  printf("S5-FIG %L objType=%L purpose=%L layer=%L bbox=%L xy=%L\n" tag f~>objType f~>purpose
         f~>layerName f~>bBox s5Get(f 'xy))
)

printf("S5-BEGIN\n")
s5Api("START")

cv = car(errset(dbOpenCellViewByType(s5Lib s5Shell "schematic" nil "a")))
printf("S5-SHELL %L shapes=%L insts=%L nets=%L\n" cv != nil
       if(cv == nil 0 length(cv~>shapes))
       if(cv == nil 0 length(cv~>instances))
       if(cv == nil 0 length(cv~>nets)))

when(cv
  let((lines labs one oneb oxy r bb n0 d1)
    ;; M4 first on shape 1, then with the working comparison build the two lists
    one = car(cv~>shapes)
    s5Cmp(one~>objType "line")
    lines = nil
    labs = nil
    foreach(f cv~>shapes
      when(s5IsStr(f~>objType "line") lines = cons(f lines))
      when(s5IsStr(f~>objType "label") labs = cons(f labs))
    )
    printf("S5-FILTER lines=%L labels=%L of shapes=%L\n" length(lines) length(labs)
           length(cv~>shapes))

    one = car(lines)
    oneb = one~>bBox
    s5Show(one "line-before")

    ;; M2 form A: dbMoveFig(cellView fig delta)
    r = car(errset(s5Move3(cv one list(0.125 0.0))))
    printf("S5-MOVE-A rc=%L bbox=%L\n" r != nil one~>bBox)
    r = car(errset(s5Move3(cv one list(-0.125 0.0))))
    printf("S5-MOVE-A-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; M2 form B: figures as a list
    r = car(errset(s5Move3L(cv list(one) list(0.125 0.0))))
    printf("S5-MOVE-B rc=%L bbox=%L\n" r != nil one~>bBox)
    s5Move3L(cv list(one) list(-0.125 0.0))
    printf("S5-MOVE-B-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; M3: assign bBox directly
    bb = list(list(3.0 0.125) list(3.0625 0.125))
    r = car(errset(s5SetBBox(one bb)))
    printf("S5-SETBBOX rc=%L want=%L got=%L\n" r != nil bb one~>bBox)
    r = car(errset(s5SetBBox(one oneb)))
    printf("S5-SETBBOX-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; M3: assign xy on a label, remembering the original xy
    one = car(labs)
    oneb = one~>bBox
    oxy = one~>xy
    bb = list(2.8 0.2)
    r = car(errset(s5SetXY(one bb)))
    printf("S5-SETXY rc=%L want=%L gotXY=%L bbox=%L\n" r != nil bb one~>xy one~>bBox)
    r = car(errset(s5SetXY(one oxy)))
    printf("S5-SETXY-UNDONE restored=%L\n" equal(oneb one~>bBox))
    s5Show(one "line-after-label")

    ;; drawing creation forms
    n0 = length(cv~>shapes)
    d1 = car(errset(s5Rect3(cv list("shape" "drawing") list(0.0 0.0 0.2 0.2))))
    printf("S5-DRAW rect(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s5Rect4(cv "shape" "drawing" list(0.0 0.0 0.2 0.2))))
    printf("S5-DRAW rect(cv,layer,purpose,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s5Rect3(cv list("shape" "drawing") list(list(0.0 0.0) list(0.2 0.2)))))
    printf("S5-DRAW rect(cv,lpp,ptlist) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s5Line3(cv list("shape" "drawing") list(0.0 0.0 0.2 0.2))))
    printf("S5-DRAW line(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s5Label3(cv list("comment" "drawing") list(0.1 0.5) "s5probe")))
    printf("S5-DRAW label(cv,lpp,pt,text) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s5Pin3(cv list("pin" "drawing") list(0.0 0.0 0.2 0.2))))
    printf("S5-DRAW pin(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    printf("S5-DRAW-SHAPES start=%L now=%L\n" n0 length(cv~>shapes))
  )
)

;; the known editor-package trigger, then re-probe what became available
printf("S5-TRIGGER %L\n" car(errset(dbCreateRect(cv))))
s5Api("AFTER-TRIGGER")

when(cv dbClose(cv))

sym = car(errset(dbOpenCellViewByType(s5Lib s5Sym "symbol" nil "r")))
printf("S5-SYM %L shapes=%L terms=%L\n" sym != nil if(sym == nil 0 length(sym~>shapes))
       if(sym == nil 0 length(sym~>terminals)))
when(sym
  foreach(f sym~>shapes
    when(s5IsStr(f~>purpose "drawing")
      when(s5IsStr(f~>objType "rect")
        when(car(car(f~>bBox)) > 0.9
          printf("S5-SYM-PINRECT bbox=%L layer=%L\n" f~>bBox f~>layerName)
        )
      )
    )
  )
  foreach(tm sym~>terminals
    printf("S5-SYM-TERM %L %L pins=%L\n" tm~>name tm~>direction length(tm~>pins))
  )
  dbClose(sym)
)

printf("S5-DONE\n")
nil
