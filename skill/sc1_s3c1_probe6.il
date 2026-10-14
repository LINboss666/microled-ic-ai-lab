;; sc1_s3c1_probe6.il
;;
;; SCAN-1 S3C1 task 2 -- final scratch session; every answer here is a new measurement, not a
;; repeat. The two bare-call errors taken together pin dbMoveFig's argument order down:
;;   probe4  dbMoveFig(fig, delta)          -> "*Error* dbMoveFig: Invalid cellView - (-0.125 0.0)"
;;           (arg2 is checked as a cellView)
;;   probe5  dbMoveFig(cv, fig, delta)      -> "*Error* dbMoveFig: Invalid figure - db:0x163de79a"
;;           (arg1 is checked as a figure)
;;   therefore the form to try is dbMoveFig( figure cellView delta ).
;; probe5 also measured: string figure attributes DO compare with both equal and == (S5-CMP
;; want="line" val="line" equal=t ste=t), which is why the filters now work (lines=9 labels=9).
;; probe5 lost its remaining results because one bare call raised, so in this file EVERY risky
;; call goes through a helper inside errset and there is not one bare call in the write tests.
;;
;; Same target as probe5: s3c_asg_shell:schematic (own helper cell, 18 shapes = 9 wire lines +
;; 9 labels, 0 terminals, 1 instance), opened in "a", every change reversed, nothing dbSave'd.
;; NEW_SIMULATION_RUNS = 0.

s6Lib   = "microled_scan_s3c"
s6Shell = "s3c_asg_shell"
s6Sym   = "sc1_s3b_p33_bank_7"

s6Names = list('dbMoveFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel 'dbCreatePin 'dbDeleteObj
               'schCheck 'schCreateWire 'schDelete 'schMaintainConn 'symUpdateInst
               'schUpdateInst 'hiCheckAndSave 'hiGetSession 'hiGetEditWin 'geGetEditCellView
               'dbSave 'dbGetFigUnder 'hiIssueMethod)

procedure(s6Get(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s6Api(stage)
  let((n)
    foreach(n s6Names printf("S6-API %L %L %L\n" stage n getd(n)))
  )
)

;; one helper per call shape; errset at the call site keeps a raise from ending the session
procedure(s6MoveFC(cv fig d)
  dbMoveFig(cv fig d)
)

procedure(s6MoveCF(fig cv d)
  dbMoveFig(fig cv d)
)

procedure(s6MoveFD(fig d)
  dbMoveFig(fig d)
)

procedure(s6SetBBox(obj v)
  obj~>bBox = v
)

procedure(s6SetXY(obj v)
  obj~>xy = v
)

procedure(s6Rect3(cv lpp pts)
  dbCreateRect(cv lpp pts)
)

procedure(s6Rect4(cv lyr pur pts)
  dbCreateRect(cv lyr pur pts)
)

procedure(s6Line3(cv lpp pts)
  dbCreateLine(cv lpp pts)
)

procedure(s6Label3(cv lpp pt txt)
  dbCreateLabel(cv lpp pt txt)
)

procedure(s6Pin3(cv lpp pts)
  dbCreatePin(cv lpp pts)
)

procedure(s6Show(f tag)
  printf("S6-FIG %L objType=%L purpose=%L layer=%L bbox=%L xy=%L\n" tag f~>objType f~>purpose
         f~>layerName f~>bBox s6Get(f 'xy))
)

printf("S6-BEGIN\n")
s6Api("START")

cv = car(errset(dbOpenCellViewByType(s6Lib s6Shell "schematic" nil "a")))
printf("S6-SHELL %L shapes=%L insts=%L nets=%L\n" cv != nil
       if(cv == nil 0 length(cv~>shapes))
       if(cv == nil 0 length(cv~>instances))
       if(cv == nil 0 length(cv~>nets)))

when(cv
  let((lines labs one oneb oxy r bb n0 d1 pts)
    lines = nil
    labs = nil
    foreach(f cv~>shapes
      when(equal(f~>objType "line") lines = cons(f lines))
      when(equal(f~>objType "label") labs = cons(f labs))
    )
    printf("S6-FILTER lines=%L labels=%L\n" length(lines) length(labs))
    one = car(lines)
    oneb = one~>bBox
    s6Show(one "line-before")

    ;; the derived order: (figure cellView delta)
    r = car(errset(s6MoveCF(one cv list(0.125 0.0))))
    printf("S6-MOVE-CF rc=%L bbox=%L\n" r != nil one~>bBox)
    r = car(errset(s6MoveCF(one cv list(-0.125 0.0))))
    printf("S6-MOVE-CF-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; the two other orders, for the record
    r = car(errset(s6MoveFC(cv one list(0.125 0.0))))
    printf("S6-MOVE-FC rc=%L bbox=%L\n" r != nil one~>bBox)
    r = car(errset(s6MoveFD(one list(0.125 0.0))))
    printf("S6-MOVE-FD rc=%L bbox=%L\n" r != nil one~>bBox)
    s6MoveCF(one cv list(-0.125 0.0))
    printf("S6-MOVE-STATE restored=%L\n" equal(oneb one~>bBox))

    ;; direct bBox assignment: the placement primitive this round would really need
    bb = list(list(3.0 0.125) list(3.0625 0.125))
    r = car(errset(s6SetBBox(one bb)))
    printf("S6-SETBBOX rc=%L want=%L got=%L\n" r != nil bb one~>bBox)
    r = car(errset(s6SetBBox(one oneb)))
    printf("S6-SETBBOX-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; direct xy assignment on a label (labels DO expose xy, probe4)
    one = car(labs)
    oneb = one~>bBox
    oxy = one~>xy
    bb = list(car(oxy) + 0.25  cadr(oxy))
    r = car(errset(s6SetXY(one bb)))
    printf("S6-SETXY rc=%L wantXY=%L gotXY=%L bbox=%L\n" r != nil bb one~>xy one~>bBox)
    r = car(errset(s6SetXY(one oxy)))
    printf("S6-SETXY-UNDONE restored=%L\n" equal(oneb one~>bBox))

    ;; creation forms
    n0 = length(cv~>shapes)
    pts = list(0.0 0.0 0.2 0.2)
    d1 = car(errset(s6Rect3(cv list("shape" "drawing") pts)))
    printf("S6-DRAW rect(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s6Rect4(cv "shape" "drawing" pts)))
    printf("S6-DRAW rect(cv,layer,purpose,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s6Rect3(cv list("shape" "drawing") list(list(0.0 0.0) list(0.2 0.2)))))
    printf("S6-DRAW rect(cv,lpp,ptlist) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s6Line3(cv list("shape" "drawing") pts)))
    printf("S6-DRAW line(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s6Label3(cv list("comment" "drawing") list(0.1 0.5) "s6probe")))
    printf("S6-DRAW label(cv,lpp,pt,text) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    d1 = car(errset(s6Pin3(cv list("pin" "drawing") pts)))
    printf("S6-DRAW pin(cv,lpp,flat) rc=%L objType=%L\n" d1 != nil
           if(d1 == nil nil d1~>objType))
    printf("S6-DRAW-SHAPES start=%L now=%L\n" n0 length(cv~>shapes))
    printf("S6-NODElete-check dbDeleteObj=%L\n" getd('dbDeleteObj) != nil)
  )
)

printf("S6-TRIGGER %L\n" car(errset(dbCreateRect(cv))))
s6Api("AFTER-TRIGGER")
when(cv dbClose(cv))

;; the delivered bank symbol, read-only: confirm pin rects are findable with string compares
sym = car(errset(dbOpenCellViewByType(s6Lib s6Sym "symbol" nil "r")))
printf("S6-SYM %L shapes=%L terms=%L\n" sym != nil if(sym == nil 0 length(sym~>shapes))
       if(sym == nil 0 length(sym~>terminals)))
when(sym
  let((pr)
    pr = 0
    foreach(f sym~>shapes
      when(equal(f~>purpose "drawing")
        when(equal(f~>objType "rect")
          when(car(car(f~>bBox)) > 0.9 pr = pr + 1)
        )
      )
    )
    printf("S6-SYM-PINRECTS %L\n" pr)
    foreach(tm sym~>terminals
      printf("S6-SYM-TERM %L %L pins=%L\n" tm~>name tm~>direction length(tm~>pins))
    )
    dbClose(sym)
  )
)

printf("S6-DONE\n")
nil
