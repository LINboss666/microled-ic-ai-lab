;; sc1_s3c1_scratch_probe.il
;;
;; SCAN-1 S3C1 task 2 -- the one scratch session allowed by "在本任务的临时副本做一次真实小例验证".
;; It answers the three questions that decide how Symbol graphics may be repositioned:
;;   Q1 dbMoveFig      -- does it take a delta, and is a move exactly reversible?
;;   Q2 dbCreateRect   -- which 3-argument form this build accepts ("3 expected, 2 given").
;;   Q3 post-editor API -- what editing functions exist once the editor package has loaded, in
;;      particular anything that keeps a parent schematic's wires attached when a symbol pin
;;      moves (schMaintainConn / symUpdateInst / schUpdateInst family).
;;
;; Writes land only on an in-memory COPY of one delivered symbol (dbCopyCellView to a scratch
;; cellview that is never dbSave'd). The delivered cells are opened read-only.
;; NEW_SIMULATION_RUNS = 0: no Spectre, no ngspice, no preflight in this file.

s3c1pLib    = "microled_scan_s3c"
s3c1pSrc    = "sc1_s3b_p33_bank_7"     ;; 3 terminals / 13 shapes: smallest symbol that has pins
s3c1pScr    = "s3c1p_scratch_sym"
s3c1pParent = "sc1_scan_power_1ch_s3c" ;; top schematic, read-only census

probeNames = list(
  'dbMoveFig 'dbRotateFig 'dbMirrorFig 'dbCopyFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel
  'dbCreatePin 'dbCreateTerm 'dbDeleteObj 'dbCreateProp 'dbSave 'dbClose
  'schCheck 'schCreateWire 'schDelete 'schMaintainConn 'symUpdateInst 'schUpdateInst
  'schChangeCellView 'schMoveInst 'geMoveSel 'geMoveFig 'hiCheckAndSave
  'hiOpenView 'hiGetSession 'hiGetEditWin 'hiGetWindow 'hiCreateWindow 'hiRedraw
  'schGetEditCellView 'hiGetWinEditCellView 'schSelectObj 'geSelectAllObjs
  'dbGetNetWires 'dbCheck 'dbCopyCellView)

procedure(s3c1pApi(stage names)
  let((n)
    foreach(n names printf("S3C1P-API %L %L %L\n" stage n getd(n)))))

;; some attributes exist only on one objType (text on labels), and a missing attribute raises
;; rather than returning nil -- errset keeps one bad field from aborting the whole dump
procedure(s3c1pGet(obj nm)
  car(errset(dbGet(obj nm))))

procedure(s3c1pFig(f what)
  if(f == nil printf("S3C1P-FIG %L NIL\n" what)
     printf("S3C1P-FIG %L %L %L %L %L %L\n" what f~>objType f~>layerName f~>purpose
            f~>bBox s3c1pGet(f 'objName))))

;; every shape as one line -- the Python side does the bucketing, so no list bookkeeping here
procedure(s3c1pShapes(cv tag)
  let((k)
    k = 0
    foreach(f cv~>shapes
      k = k + 1
      printf("S3C1P-SHAPE %L %L %L %L %L %L %L %L\n" tag k f~>objType f~>layerName f~>purpose
             f~>bBox s3c1pGet(f 'objName) s3c1pGet(f 'text)))))

printf("S3C1P-BEGIN\n")
s3c1pApi("BEFORE-VIEWS" probeNames)

src = car(errset(dbOpenCellViewByType(s3c1pLib s3c1pSrc "symbol" nil "r")))
printf("S3C1P-SRC-OPEN %L\n" src != nil)
when(src
  printf("S3C1P-SRC-COUNTS shapes=%L terms=%L\n" length(src~>shapes) length(src~>terminals))
  s3c1pShapes(src "src-symbol")
  foreach(term src~>terminals
    printf("S3C1P-TERM %L %L %L pins=%L\n" term~>name term~>direction
           if(term~>net term~>net~>name 'NO_NET) length(term~>pins))
    foreach(p term~>pins
      printf("S3C1P-PIN %L %L figs=%L\n" term~>name p~>direction length(p~>figs))
      foreach(f p~>figs s3c1pFig(f "pinfig")))))

when(getd('dbCopyCellView)
  scratch = car(errset(dbCopyCellView(src s3c1pLib s3c1pScr "symbol" "s3c1 scratch probe")))
  printf("S3C1P-SCRATCH %L %L\n" scratch != nil if(scratch == nil nil scratch~>viewType))
  when(scratch
    ;; Q1: move one pin figure by a delta, then the negated delta, and compare bboxes
    targetFig = nil
    foreach(term scratch~>terminals
      when(targetFig == nil
        foreach(p term~>pins
          foreach(f p~>figs
            when(targetFig == nil and f~>objType == 'rect targetFig = f))))
    when(targetFig
      before = targetFig~>bBox
      mv = car(errset(dbMoveFig(targetFig list(0.05 0.05))))
      printf("S3C1P-MOVE1 rc=%L before=%L after=%L\n" mv != nil before targetFig~>bBox)
      back = car(errset(dbMoveFig(targetFig list(-0.05 -0.05))))
      printf("S3C1P-MOVE2 rc=%L restored=%L\n" back != nil targetFig~>bBox)
      printf("S3C1P-MOVE-REVERSIBLE %L\n" equal(before targetFig~>bBox))
      s3c1pFig(targetFig "after-roundtrip"))

    lab = nil
    foreach(f scratch~>shapes when(lab == nil and f~>objType == 'label lab = f))
    when(lab
      b1 = lab~>bBox
      printf("S3C1P-LABEL before=%L text=%L objType=%L\n" b1 lab~>text lab~>objType)
      printf("S3C1P-LABEL-MOVE rc=%L after=%L\n"
             car(errset(dbMoveFig(lab list(0.1 0.0)))) != nil lab~>bBox)
      dbMoveFig(lab list(-0.1 0.0))
      printf("S3C1P-LABEL-RESTORED equal=%L\n" equal(b1 lab~>bBox)))

    ;; Q2: dbCreateRect forms, each inside errset but logged one per line so a partial
    ;; success is still visible in the shape count
    pts2 = list(list(0.2 0.2) (0.7 0.7))
    pts4 = list(0.2 0.2 0.7 0.7)
    printf("S3C1P-RECT f1(cv,2pt,nil) => %L\n" car(errset(dbCreateRect(scratch pts2 nil))) != nil)
    printf("S3C1P-RECT f2(cv,2pt,name) => %L\n"
           car(errset(dbCreateRect(scratch pts2 "probeA"))) != nil)
    printf("S3C1P-RECT f3(cv,flat,nil) => %L\n" car(errset(dbCreateRect(scratch pts4 nil))) != nil)
    printf("S3C1P-RECT f4(cv,2pt,lpp,purpose) => %L\n"
           car(errset(dbCreateRect(scratch pts2 "m1Metal" "drawing"))) != nil)
    printf("S3C1P-RECT-SHAPES-NOW %L\n" length(scratch~>shapes))
    printf("S3C1P-SCRATCH-SAVED no\n")
    dbClose(scratch)))

s3c1pApi("AFTER-CALLS" probeNames)

par = car(errset(dbOpenCellViewByType(s3c1pLib s3c1pParent "schematic" nil "r")))
printf("S3C1P-PARENT-OPEN %L\n" par != nil)
when(par
  printf("S3C1P-PARENT-COUNTS shapes=%L insts=%L terms=%L\n" length(par~>shapes)
         length(par~>instances) length(par~>terminals))
  s3c1pShapes(par "parent-schematic")
  foreach(i par~>instances
    printf("S3C1P-INST %L %L bbox=%L instTerms=%L\n" i~>cellName i~>name i~>bBox
           length(i~>instTerms)))
  foreach(t2 par~>terminals
    printf("S3C1P-PTERM %L %L %L pins=%L\n" t2~>name t2~>direction
           if(t2~>net t2~>net~>name 'NO_NET) length(t2~>pins)))
  when(getd('schCheck) printf("S3C1P-PARENT-SCHCHECK %L\n" errset(schCheck(par))))
  dbClose(par))

when(src != nil dbClose(src))
printf("S3C1P-DONE\n")
nil
