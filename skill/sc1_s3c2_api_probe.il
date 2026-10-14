;; sc1_s3c2_api_probe.il
;;
;; SCAN-1 S3C2 section 3 -- call the DOCUMENTED interfaces, on this task's own temporary copies, and
;; record the call, the returned object and the object-count change for each. Three things the S3C1
;; round got wrong are corrected here rather than re-guessed:
;;   1  the delete function is dbDeleteObject, not dbDeleteObj -- getd('dbDeleteObj)=nil proved
;;      nothing about delete capability;
;;   2  dbMoveFig's third argument is a TRANSFORM (origin point, direction, optional scale), not a
;;      bare (dx dy) list, which is why every S3C1 order returned nil;
;;   3  the create calls were tried with a layer that does not exist in these views ("shape"), so
;;      "six forms failed" overstates the measurement. Here each create uses an lpp the target view
;;      already carries, and the label form gets alignment / direction / font / size.
;;
;; A raised error still reaches the session log even when the call is inside errset (measured in
;; S3C1: the arity error text printed while errset suppressed only the abort), so nothing here needs
;; a bare call that would end the session, and no failure is reported as rc=nil alone.
;;
;; Targets are two scratch cellviews copied out of the delivered ones (s3c2_scratch_sym:symbol and
;; s3c2_scratch_sch:schematic). The delivered views are opened read-only and are not modified by
;; this file. The scratch cellviews are deleted again at the end of the step.
;; NEW_SIMULATION_RUNS = 0.

s2Lib    = "microled_scan_s3c"
s2SymSrc = "sc1_s3b_p33_bank_7"
s2SchSrc = "sc1_scan_power_1ch_s3c"
s2SymScr = "s3c2_scratch_sym"
s2SchScr = "s3c2_scratch_sch"

procedure(s2Get(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s2Val(v)
  if(v == nil "NONE" v)
)

procedure(s2Counts(cv tag)
  printf("S2-COUNT %L shapes=%L insts=%L terms=%L nets=%L pins=%L\n" tag length(cv~>shapes)
         length(cv~>instances) length(cv~>terminals) length(cv~>nets)
         car(errset(let((k k2)
           k = 0
           foreach(k2 cv~>terminals foreach(p k2~>pins k = k + 1))
           k)))
  )
)

procedure(s2Show(f tag)
  printf("S2-FIG %L objType=%L lpp=%L/%L bbox=%L\n" tag f~>objType f~>layerName f~>purpose f~>bBox)
)

procedure(s2Yof(f)
  let((b)
    b = f~>bBox
    if(b == nil 0.0 (car(car(b)) + cadr(car(b)) + car(cadr(b)) + cadr(cadr(b))) / 4.0)
  )
)

procedure(s2SetNet(obj net)
  obj~>net = net
)

;; the three graphics that make one symbol pin: the pin rectangle on pin/drawing, the stub on
;; device/drawing and the name on pin/label, all sharing the pin centre y
procedure(s2PinGroup(cv tm)
  let((rect stub name)
    rect = nil
    stub = nil
    name = nil
    foreach(p tm~>pins
      foreach(f p~>figs
        when(equal(f~>purpose "drawing")
          when(equal(f~>layerName "pin") rect = f)
        )
      )
    )
    when(rect != nil
      let((ry)
        ry = s2Yof(rect)
        foreach(f cv~>shapes
          when(equal(f~>objType "line")
            when(equal(f~>layerName "device")
              when(abs(s2Yof(f) - ry) < 0.02 stub = f)
            )
          )
          when(equal(f~>objType "label")
            when(equal(f~>layerName "pin")
              when(abs(s2Yof(f) - ry) < 0.02 name = f)
            )
          )
        )
      )
    )
    list(rect stub name)
  )
)

procedure(s2MoveTest(cv)
  let((tm g rect stub name b1 b2 b3 r tr neg)
    tm = car(cv~>terminals)
    g = s2PinGroup(cv tm)
    rect = car(g)
    stub = cadr(g)
    name = caddr(g)
    printf("S2-MOVE-GROUP term=%L rect=%L stub=%L label=%L\n" tm~>name rect != nil stub != nil
           name != nil)
    when(rect == nil printf("S2-MOVE ABORT no pin rectangle found\n"))
    when(rect != nil
      b1 = rect~>bBox
      tr = list(list(0.125 0.0) "R0" 1.0)
      r = car(errset(dbMoveFig(rect cv tr)))
      b2 = rect~>bBox
      printf("S2-MOVEFIG-A rc=%L result=%L before=%L after=%L\n" r != nil type(r) b1 b2)
      neg = list(list(-0.125 0.0) "R0" 1.0)
      r = car(errset(dbMoveFig(rect cv neg)))
      b3 = rect~>bBox
      printf("S2-MOVEFIG-B rc=%L restored=%L equal=%L\n" r != nil b3 equal(b1 b3))
      ;; the two members that have to follow the pin: stub and name
      when(stub != nil
        let((sb)
          sb = stub~>bBox
          printf("S2-MOVE-STUB before=%L\n" sb)
          r = car(errset(dbMoveFig(stub cv tr)))
          printf("S2-MOVE-STUB rc=%L after=%L\n" r != nil stub~>bBox)
          dbMoveFig(stub cv neg)
          printf("S2-MOVE-STUB-UNDONE equal=%L\n" equal(sb stub~>bBox))
        )
      )
      when(name != nil
        let((y)
          y = s2Yof(name)
          printf("S2-MOVE-LABEL before=%L xy=%L text=%L just=%L\n" name~>bBox name~>xy
                 s2Get(name 'text) s2Get(name 'justification))
          r = car(errset(dbMoveFig(name cv tr)))
          printf("S2-MOVE-LABEL rc=%L after=%L xy=%L\n" r != nil name~>bBox name~>xy)
          dbMoveFig(name cv neg)
          printf("S2-MOVE-LABEL-UNDONE %L\n" equal(y s2Yof(name)))
        )
      )
    )
  )
)

procedure(s2CreateTest(cv lppRect lppLine)
  let((n0 r ln lab net pin p0)
    n0 = length(cv~>shapes)
    r = car(errset(dbCreateRect(cv lppRect list(list(3.0 3.0) list(3.2 3.1)))))
    printf("S2-CREATE rect %L rc=%L objType=%L bbox=%L\n" lppRect r != nil
           if(r == nil nil r~>objType) if(r == nil nil r~>bBox))
    ln = car(errset(dbCreateLine(cv lppLine list(list(3.0 3.2) list(3.6 3.2)))))
    printf("S2-CREATE line %L rc=%L objType=%L bbox=%L\n" lppLine ln != nil
           if(ln == nil nil ln~>objType) if(ln == nil nil ln~>bBox))
    lab = car(errset(dbCreateLabel(cv list("pin" "label") list(3.0 3.3) "s2probe" "centerLeft"
                                            "R0" "stick" 0.0625)))
    printf("S2-CREATE label rc=%L objType=%L bbox=%L text=%L just=%L\n" lab != nil
           if(lab == nil nil lab~>objType) if(lab == nil nil lab~>bBox)
           if(lab == nil nil s2Get(lab 'text)) if(lab == nil nil s2Get(lab 'justification)))
    ;; a pin needs a NET object and a FIGURE object, not a cellview plus a layer
    p0 = length(cv~>terminals)
    net = car(errset(dbMakeNet(cv "s2_probe_net")))
    printf("S2-MAKENET rc=%L objType=%L name=%L nets=%L\n" net != nil if(net == nil nil type(net))
           if(net == nil nil s2Get(net 'name)) length(cv~>nets))
    when(net != nil
      when(r != nil
        pin = car(errset(dbCreatePin(net r "s2_probe_net")))
        printf("S2-CREATEPIN rc=%L objType=%L terminals %L -> %L\n" pin != nil
               if(pin == nil nil pin~>objType) p0 length(cv~>terminals))
        when(pin != nil
          printf("S2-PIN-NET %L\n" if(pin~>net pin~>net~>name 'NO_NET))
        )
      )
    )
    ;; delete: the documented name is dbDeleteObject
    when(ln != nil
      let((n1)
        n1 = length(cv~>shapes)
        printf("S2-DELETEOBJ before=%L\n" n1)
        r = car(errset(dbDeleteObject(ln)))
        printf("S2-DELETEOBJ rc=%L shapes %L -> %L\n" r != nil n1 length(cv~>shapes))
      )
    )
    printf("S2-CREATE-SHAPES start=%L now=%L\n" n0 length(cv~>shapes))
    list(r lab net pin)
  )
)

printf("S2-BEGIN\n")
printf("S2-DBDeleteObject=%L dbMakeNet=%L dbCreatePin=%L dbMoveFig=%L\n" getd('dbDeleteObject)
       getd('dbMakeNet) getd('dbCreatePin) getd('dbMoveFig))

symSrc = car(errset(dbOpenCellViewByType(s2Lib s2SymSrc "symbol" nil "r")))
printf("S2-SRC-SYM %L\n" symSrc != nil)
sym = car(errset(dbCopyCellView(symSrc s2Lib s2SymScr "symbol" nil)))
printf("S2-SCRATCH-SYM %L\n" sym != nil)
when(sym == nil
  printf("S2-SCRATCH-SYM-REOPEN %L\n"
         car(errset(dbOpenCellViewByType(s2Lib s2SymScr "symbol" nil "a"))) != nil)
  sym = car(errset(dbOpenCellViewByType(s2Lib s2SymScr "symbol" nil "a")))
)
when(sym != nil
  s2Counts(sym "sym-new")
  printf("S2-LPP %L\n" let((out)
    out = nil
    foreach(f sym~>shapes
      out = cons(list(f~>layerName f~>purpose) out)
    )
    out))
  s2MoveTest(sym)
  s2CreateTest(sym list("device" "drawing") list("device" "drawing"))
  printf("S2-SYM-SAVE %L\n" car(errset(dbSave(sym))) != nil)
  printf("S2-SYM-CLOSE %L\n" car(errset(dbClose(sym))) != nil)

  rsym = car(errset(dbOpenCellViewByType(s2Lib s2SymScr "symbol" nil "r")))
  printf("S2-SYM-REOPEN %L\n" rsym != nil)
  when(rsym != nil
    s2Counts(rsym "sym-reopened")
    foreach(tm2 rsym~>terminals
      printf("S2-RT %L %L pins=%L\n" tm2~>name tm2~>direction length(tm2~>pins))
      foreach(p tm2~>pins
        foreach(f p~>figs s2Show(f "reopened-pinfig"))
      )
    )
    dbClose(rsym)
  )
)

schSrc = car(errset(dbOpenCellViewByType(s2Lib s2SchSrc "schematic" nil "r")))
printf("S2-SRC-SCH %L\n" schSrc != nil)
sch = car(errset(dbCopyCellView(schSrc s2Lib s2SchScr "schematic" "schematic")))
printf("S2-SCRATCH-SCH %L\n" sch != nil)
when(sch == nil
  sch = car(errset(dbOpenCellViewByType(s2Lib s2SchScr "schematic" "schematic" "a")))
  printf("S2-SCRATCH-SH-REOPEN %L\n" sch != nil)
)
when(sch != nil
  s2Counts(sch "sch-new")
  printf("S2-SCH-LPP %L\n" let((out)
    out = nil
    foreach(f sch~>shapes
      out = cons(list(f~>layerName f~>purpose) out)
    )
    out))
  keep = s2CreateTest(sch list("wire" "drawing") list("wire" "drawing"))
  ;; can a drawn figure be given the net it is supposed to carry, by assignment?
  when(car(keep) != nil
    let((n obj)
      n = caddr(keep)
      obj = car(keep)
      when(n != nil
        r = car(errset(s2SetNet(obj n)))
        printf("S2-SETNET-ASSIGN rc=%L want=%L got=%L\n" r != nil n~>name
               s2Val(if(obj~>net obj~>net~>name nil)))
      )
    )
  )
  printf("S2-SCH-SAVE %L\n" car(errset(dbSave(sch))) != nil)
  printf("S2-SCH-CLOSE %L\n" car(errset(dbClose(sch))) != nil)
  rsch = car(errset(dbOpenCellViewByType(s2Lib s2SchScr "schematic" "schematic" "r")))
  printf("S2-SCH-REOPEN %L\n" rsch != nil)
  when(rsch != nil
    s2Counts(rsch "sch-reopened")
    dbClose(rsch)
  )
)

when(schSrc != nil dbClose(schSrc))
when(symSrc != nil dbClose(symSrc))
printf("S2-DONE\n")
nil
