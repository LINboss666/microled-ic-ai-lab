;; sc1_s3c1_scratch_probe2.il
;;
;; SCAN-1 S3C1 task 2 -- the scratch session allowed by
;; "在本任务的临时副本做一次真实小例验证，成功后直接应用，不重复环境探索".
;; The first attempt (skill/sc1_s3c1_scratch_probe.il) aborted on a parenthesis imbalance in
;; this file, not on a Cadence limit; it is replaced by this flat version.
;;
;; Questions answered:
;;   Q1 dbMoveFig      -- delta semantics, and is a move exactly reversible?
;;   Q2 dbCreateRect / dbCreateLine / dbCreateLabel / dbCreatePin -- which argument form this
;;      build accepts (an earlier 2-argument call failed with "too few arguments (3 expected,
;;      2 given)"; the community form is (cellView lpp points)).
;;   Q3 post-editor API -- which editing functions exist once the editor package has loaded, in
;;      particular anything that keeps a parent schematic's wires attached when a symbol pin
;;      moves (schMaintainConn / symUpdateInst / schUpdateInst family).
;;
;; Writes land only on a COPY of one delivered symbol (dbCopyCellView to a scratch cellview that
;; is never dbSave'd). Measured in probe1: dbCopyCellView itself creates the cellview on disk, so
;; the scratch name is fresh per run and the scratch directories are deleted again afterwards; the
;; library digest list taken before the run is compared afterwards to prove the delivered files
;; were not touched.
;; NEW_SIMULATION_RUNS = 0: no Spectre, no ngspice, no preflight in this file.

s3c1pLib    = "microled_scan_s3c"
s3c1pSrc    = "sc1_s3b_p33_bank_7"     ;; 3 terminals / 13 shapes: smallest symbol with pins
s3c1pScr    = "s3c1p_scratch_sym2"   ;; probe1 proved dbCopyCellView lands on disk without
                                     ;; dbSave, so each run takes a fresh name and the scratch
                                     ;; directories are removed again at the end of the round
s3c1pParent = "sc1_scan_power_1ch_s3c" ;; top schematic, read-only census

s3c1pNames = list(
  'dbMoveFig 'dbRotateFig 'dbMirrorFig 'dbCopyFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel
  'dbCreatePin 'dbCreateTerm 'dbDeleteObj 'dbCreateProp 'dbSave 'dbClose
  'ddCreateRect 'schCheck 'schCreateWire 'schDelete 'schMaintainConn 'symUpdateInst
  'schUpdateInst 'schChangeCellView 'schMoveInst 'geMoveSel 'geMoveFig 'hiCheckAndSave
  'hiOpenView 'hiGetSession 'hiGetEditWin 'hiGetWindow 'hiCreateWindow 'hiRedraw
  'geGetEditCellView 'schGetEditCellView 'hiGetWinEditCellView 'schSelectObj 'geSelectAllObjs
  'dbGetNetWires 'dbCheck 'dbCopyCellView)

procedure(s3c1pApi(stage names)
  let((n)
    foreach(n names printf("S3C1P-API %L %L %L\n" stage n getd(n)))
  )
)

procedure(s3c1pGet(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s3c1pLine(f what)
  if(f == nil
     printf("S3C1P-FIG %L NIL\n" what)
     printf("S3C1P-FIG %L %L %L %L %L\n" what f~>objType f~>layerName f~>purpose f~>bBox)
  )
)

procedure(s3c1pShapes(cv tag)
  let((k)
    k = 0
    foreach(f cv~>shapes
      k = k + 1
      printf("S3C1P-SHAPE %L %L %L %L %L %L %L %L\n" tag k f~>objType f~>layerName f~>purpose
             f~>bBox s3c1pGet(f 'objName) s3c1pGet(f 'text))
    )
  )
)

procedure(s3c1pTerms(cv tag)
  let((nm)
    foreach(tm cv~>terminals
      nm = if(tm~>net tm~>net~>name 'NO_NET)
      printf("S3C1P-TERM %L %L %L %L pins=%L\n" tag tm~>name tm~>direction nm length(tm~>pins))
      foreach(p tm~>pins
        printf("S3C1P-PIN %L %L %L dir=%L figs=%L\n" tag tm~>name p~>direction
               s3c1pGet(p 'direction) length(p~>figs))
        foreach(f p~>figs s3c1pLine(f "pinfig"))
      )
    )
  )
)

printf("S3C1P-BEGIN\n")
s3c1pApi("BEFORE-VIEWS" s3c1pNames)

src = car(errset(dbOpenCellViewByType(s3c1pLib s3c1pSrc "symbol" nil "r")))
printf("S3C1P-SRC-OPEN %L\n" src != nil)
when(src
  printf("S3C1P-SRC-COUNTS shapes=%L terms=%L\n" length(src~>shapes) length(src~>terminals))
  s3c1pShapes(src "src-symbol")
  s3c1pTerms(src "src")
)

scratch = car(errset(dbCopyCellView(src s3c1pLib s3c1pScr "symbol" nil)))
printf("S3C1P-SCRATCH %L\n" scratch != nil)

;; Q1: one pin figure out by a delta, then the negated delta, bboxes compared
when(scratch
  let((pins one b1 b2 back b3)
    pins = nil
    foreach(f scratch~>shapes
      when( (f~>objType == 'rect and f~>purpose == 'drawing and f~>bBox != nil and
             car(car(f~>bBox)) > 0.9)
        pins = cons(f pins)
      )
    )
    printf("S3C1P-PINRECTS %L\n" length(pins))
    when(pins != nil
      one = car(pins)
      b1 = one~>bBox
      back = car(errset(dbMoveFig(one list(0.05 0.05))))
      b2 = one~>bBox
      printf("S3C1P-MOVE1 rc=%L before=%L after=%L\n" back != nil b1 b2)
      back = car(errset(dbMoveFig(one list(-0.05 -0.05))))
      b3 = one~>bBox
      printf("S3C1P-MOVE2 rc=%L restored=%L\n" back != nil b3)
      printf("S3C1P-MOVE-REVERSIBLE %L\n" equal(b1 b3))
      s3c1pLine(one "after-roundtrip")
    )
  )
)

;; Q1b: a label and a connector line move the same way
when(scratch
  let((lab ln b1)
    lab = nil
    ln = nil
    foreach(f scratch~>shapes
      when( (f~>objType == 'label and lab == nil) lab = f)
      when( (f~>objType == 'line and ln == nil) ln = f)
    )
    when(lab
      b1 = lab~>bBox
      printf("S3C1P-LABEL before=%L text=%L\n" b1 s3c1pGet(lab 'text))
      printf("S3C1P-LABEL-MOVE rc=%L after=%L\n"
             car(errset(dbMoveFig(lab list(0.1 0.0)))) != nil lab~>bBox)
      dbMoveFig(lab list(-0.1 0.0))
      printf("S3C1P-LABEL-RESTORED %L\n" equal(b1 lab~>bBox))
    )
    when(ln
      b1 = ln~>bBox
      printf("S3C1P-LINE before=%L lpp=%L/%L\n" b1 ln~>layerName ln~>purpose)
      printf("S3C1P-LINE-MOVE rc=%L after=%L\n"
             car(errset(dbMoveFig(ln list(0.1 0.0)))) != nil ln~>bBox)
      dbMoveFig(ln list(-0.1 0.0))
      printf("S3C1P-LINE-RESTORED %L\n" equal(b1 ln~>bBox))
    )
  )
)

;; Q2: drawing forms, one printf per form so a raise in one cannot hide the others
when(scratch
  let((n0 pts pp l1)
    n0 = length(scratch~>shapes)
    pts = list(0.2 0.2 0.7 0.7)
    pp = list(list(0.2 0.2) list(0.7 0.7))
    l1 = car(errset(dbCreateRect(scratch list("pin" "drawing") pts)))
    printf("S3C1P-RECT a(cv,lpp,flat) rc=%L obj=%L shapes=%L\n" l1 != nil
           if(l1 == nil nil l1~>objType) length(scratch~>shapes))
    l1 = car(errset(dbCreateRect(scratch list("shape" "drawing") pp)))
    printf("S3C1P-RECT b(cv,lpp,ptlist) rc=%L obj=%L shapes=%L\n" l1 != nil
           if(l1 == nil nil l1~>objType) length(scratch~>shapes))
    l1 = car(errset(dbCreateRect(scratch "pt" pts)))
    printf("S3C1P-RECT c(cv,sym,flat) rc=%L shapes=%L\n" l1 != nil length(scratch~>shapes))
    l1 = car(errset(dbCreateLine(scratch list("pin" "drawing") pts)))
    printf("S3C1P-LINE-NEW a(cv,lpp,flat) rc=%L obj=%L shapes=%L\n" l1 != nil
           if(l1 == nil nil l1~>objType) length(scratch~>shapes))
    l1 = car(errset(dbCreateLabel(scratch list("pin" "label") list(0.5 0.5) "probe" "centerRight")))
    printf("S3C1P-LABEL-NEW a(cv,lpp,pt,text,just) rc=%L obj=%L shapes=%L\n" l1 != nil
           if(l1 == nil nil l1~>objType) length(scratch~>shapes))
    l1 = car(errset(dbCreatePin(scratch list("pin" "drawing") pts)))
    printf("S3C1P-PIN-NEW a(cv,lpp,flat) rc=%L obj=%L shapes=%L\n" l1 != nil
           if(l1 == nil nil l1~>objType) length(scratch~>shapes))
    printf("S3C1P-DRAW-DONE start=%L now=%L\n" n0 length(scratch~>shapes))
  )
)

printf("S3C1P-SCRATCH-SAVED no\n")
when(scratch dbClose(scratch))

s3c1pApi("AFTER-CALLS" s3c1pNames)

par = car(errset(dbOpenCellViewByType(s3c1pLib s3c1pParent "schematic" nil "r")))
printf("S3C1P-PARENT-OPEN %L\n" par != nil)
when(par
  printf("S3C1P-PARENT-COUNTS shapes=%L insts=%L terms=%L\n" length(par~>shapes)
         length(par~>instances) length(par~>terminals))
  s3c1pShapes(par "parent-schematic")
  s3c1pTerms(par "parent")
  let((n)
    n = 0
    foreach(i par~>instances
      n = n + 1
      printf("S3C1P-INST %L %L %L bbox=%L instTerms=%L\n" n i~>cellName i~>name i~>bBox
             length(i~>instTerms))
    )
  )
  when(getd('schCheck) printf("S3C1P-PARENT-SCHCHECK %L\n" errset(schCheck(par))))
  dbClose(par)
)

when(src != nil dbClose(src))
printf("S3C1P-DONE\n")
nil
