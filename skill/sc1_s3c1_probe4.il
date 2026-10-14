;; sc1_s3c1_probe4.il
;;
;; SCAN-1 S3C1 task 2, attempt 2 of the scratch verification (3 attempts allowed).
;; probe3 ran to completion but its write tests were skipped for two measured reasons, and this
;; file exists to settle them:
;;   F1  dbCopyCellView's copy reported 13 shapes yet NO shape matched objType=='rect' / 'label'
;;       / 'line', so the pin filter returned 0 and dbMoveFig was never exercised. The copy is
;;       therefore not a usable scratch target as written -- measured, not assumed.
;;   F2  all six dbCreateRect / dbCreateLine / dbCreateLabel / dbCreatePin calls on the copy
;;       returned nil with NO *Error* line at all (silently refused), and in this session
;;       schCheck / schCreateWire / schDelete / symUpdateInst stayed nil both before and after.
;;
;; Targets: s3c_asg_shell:schematic -- a helper cell this task created in S3-C, 18 shapes and
;; 0 terminals, NOT one of the eight delivered cells, and microled_scan_s3c:s3c_asg_shell is
;; inside the one writable library. The delivered bank symbol is opened read-only and is only
;; read here; nothing is dbSave'd by this file, and the library digest list is re-taken after.
;; NEW_SIMULATION_RUNS = 0.

s3c1qLib    = "microled_scan_s3c"
s3c1qShell  = "s3c_asg_shell"          ;; own helper cell, 18 shapes, 0 terminals
s3c1qSym    = "sc1_s3b_p33_bank_7"     ;; delivered symbol, opened "r" here
s3c1qScr    = "s3c1q_scratch_sym"

s3c1qNames = list(
  'dbMoveFig 'dbCreateRect 'dbCreateLine 'dbCreateLabel 'dbCreatePin 'dbCreateFig 'dbDeleteObj
  'schCheck 'schCreateWire 'schDelete 'schMaintainConn 'symUpdateInst 'schUpdateInst
  'hiCheckAndSave 'hiGetSession 'hiGetEditWin 'hiGetWindow 'hiCreateWindow 'geGetEditCellView
  'dbSave 'dbCopyCellView 'ddCreateRect 'geMoveFig)

procedure(s3c1qApi(stage)
  let((n)
    foreach(n s3c1qNames printf("S3C1Q-API %L %L %L\n" stage n getd(n)))
  )
)

;; objType/purpose printed WITH their SKILL type so a symbol-vs-string mix-up is visible
procedure(s3c1qDump(cv tag)
  let((k ot pu)
    k = 0
    foreach(f cv~>shapes
      k = k + 1
      ot = f~>objType
      pu = f~>purpose
      printf("S3C1Q-SHAPE %L %L objType=%L type=%L purpose=%L ptype=%L bbox=%L xy=%L\n"
             tag k ot type(ot) pu type(pu) f~>bBox s3c1qGet(f 'xy))
    )
    printf("S3C1Q-DUMP-END %L shapes=%L\n" tag k)
  )
)

procedure(s3c1qGet(obj nm)
  car(errset(dbGet(obj nm)))
)

printf("S3C1Q-BEGIN\n")
s3c1qApi("START")

shell = car(errset(dbOpenCellViewByType(s3c1qLib s3c1qShell "schematic" nil "a")))
printf("S3C1Q-SHELL %L shapes=%L terms=%L insts=%L nets=%L\n" shell != nil
       if(shell == nil 0 length(shell~>shapes))
       if(shell == nil 0 length(shell~>terminals))
       if(shell == nil 0 length(shell~>instances))
       if(shell == nil 0 length(shell~>nets)))
when(shell s3c1qDump(shell "shell"))

;; F1: what does a dbCopyCellView target actually look like?
sym = car(errset(dbOpenCellViewByType(s3c1qLib s3c1qSym "symbol" nil "r")))
printf("S3C1Q-SYM %L shapes=%L\n" sym != nil if(sym == nil 0 length(sym~>shapes)))
when(sym
  let((cp)
    cp = car(errset(dbCopyCellView(sym s3c1qLib s3c1qScr "symbol" nil)))
    printf("S3C1Q-COPY %L type=%L cellName=%L viewClass=%L viewType=%L shapes=%L\n" cp != nil
           type(cp) s3c1qGet(cp 'cellName) s3c1qGet(cp 'viewClass) s3c1qGet(cp 'viewType)
           if(cp == nil 0 length(cp~>shapes)))
    when(cp s3c1qDump(cp "copy"))
    when(cp dbClose(cp))
  )
)

;; F3: dbMoveFig on the shell's own figures -- move, measure, undo, measure.
when(shell
  let((f ot b1 b2 b3 ok)
    f = car(shell~>shapes)
    ot = f~>objType
    b1 = f~>bBox
    printf("S3C1Q-TARGET objType=%L bbox=%L\n" ot b1)
    ok = car(errset(dbMoveFig(f list(0.125 0.125))))
    b2 = f~>bBox
    printf("S3C1Q-MOVE1 rc=%L result=%L before=%L after=%L\n" ok != nil type(ok) b1 b2)
    ok = car(errset(dbMoveFig(f list(-0.125 -0.125))))
    b3 = f~>bBox
    printf("S3C1Q-MOVE2 rc=%L after=%L\n" ok != nil b3)
    printf("S3C1Q-MOVE-REVERSIBLE %L\n" equal(b1 b3))
    ;; second figure of a different objType, to show the call is not rect-specific
    let((g)
      g = nil
      foreach(f2 shell~>shapes
        when(g == nil
          when(f2~>objType != ot g = f2)
        )
      )
      when(g
        let((gb)
          gb = g~>bBox
          printf("S3C1Q-MOVE-OTHER objType=%L before=%L\n" g~>objType gb)
          printf("S3C1Q-MOVE-OTHER moved=%L\n"
                 car(errset(dbMoveFig(g list(0.125 0.0)))) != nil)
          printf("S3C1Q-MOVE-OTHER after=%L\n" g~>bBox)
          dbMoveFig(g list(-0.125 0.0))
          printf("S3C1Q-MOVE-OTHER-UNDONE %L\n" equal(gb g~>bBox))
        )
      )
    )
  )
)

;; F2 repeat on the shell (a real editable cellview opened in "a", not a copy)
when(shell
  let((r l1 lb pn)
    r = car(errset(dbCreateRect(shell list("shape" "drawing") list(0.0 0.0 0.5 0.5))))
    printf("S3C1Q-DRAW rect(cv,lpp,flat) rc=%L objType=%L\n" r != nil
           if(r == nil nil r~>objType))
    r = car(errset(dbCreateRect(shell list("shape" "drawing")
                                list(list(0.0 0.0) list(0.5 0.5)))))
    printf("S3C1Q-DRAW rect(cv,lpp,ptlist) rc=%L objType=%L\n" r != nil
           if(r == nil nil r~>objType))
    r = car(errset(dbCreateLine(shell list("shape" "drawing") list(0.0 0.0 0.5 0.5))))
    printf("S3C1Q-DRAW line(cv,lpp,flat) rc=%L objType=%L\n" r != nil
           if(r == nil nil r~>objType))
    r = car(errset(dbCreateLabel(shell list("comment" "drawing") list(0.1 0.1) "qprobe"
                                 "centerLeft")))
    printf("S3C1Q-DRAW label(cv,lpp,pt,text,just) rc=%L objType=%L\n" r != nil
           if(r == nil nil r~>objType))
    r = car(errset(dbCreatePin(shell list("pin" "input") list(0.0 0.0 0.5 0.5))))
    printf("S3C1Q-DRAW pin(cv,lpp,flat) rc=%L objType=%L\n" r != nil
           if(r == nil nil r~>objType))
    printf("S3C1Q-DRAW-SHAPES %L\n" length(shell~>shapes))
  )
)

;; the known trigger: a deliberately wrong-arity dbCreateRect, then re-probe the editor package
printf("S3C1Q-TRIGGER %L\n" car(errset(dbCreateRect(shell))))
s3c1qApi("AFTER-TRIGGER")

printf("S3C1Q-SAVED none\n")
when(shell dbClose(shell))
when(sym dbClose(sym))
printf("S3C1Q-DONE\n")
nil
