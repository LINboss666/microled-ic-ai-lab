; SCAN-1 S3-C1 section 2/4: the decisive capability probe -- the editor package loads LATE on this
; build, so an entry point that was nil at startup has to be tested again after a view is touched.
;
; Why: the previous session printed getd('schCheck)=nil at startup and at "after the views were
; opened", yet its own log shows `Loading schematic.cxt / lx.cxt / lce.cxt' right after the first
; drawing call. A package that arrives that late is invisible to a getd taken before it, so the S3-C
; statements "the batch session cannot draw" and "the editor check needs a GUI" were conclusions from
; the wrong measurement point -- exactly what section 2 asks to correct.
;
; This file answers four questions in one session, and nothing beyond them:
;   P1 does the schematic editor package load in a batch (-nograph) session, and when?
;   P2 can a graphic be created here, with which argument shape (three documented forms tried, the
;      error text kept from the log, the cellview used is the importer SHELL, not a delivered cell)?
;   P3 can a terminal's logical direction be set so that it survives dbSave -- on
;      sc1_s3b_p33_bank_7:symbol, whose three terminals are the smallest delivered port set. This is
;      metadata only: no shape is created, moved or deleted, and setting it back to inputOutput is
;      the exact inverse. The full library was archived first (backup_microled_scan_s3c_pre_s3c1_*).
;   P4 does the editor's own check run once the package is loaded.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_editor_probe.il 700 S3C1E_DONE
printf("S3C1E-BEGIN\n")
LIB = "microled_scan_s3c"

procedure(s3c1eApi(stage)
  let((fn)
    foreach(fn list('schCheck 'schCreate 'schCreateWire 'schCreateRect 'schCreateLine
                   'schCreateLabel 'hiCheckAndSave 'hiGetWindow 'dbDeleteObj 'dbCreateRect
                   'dbMoveFig 'dbSave 'synCheck 'schOpenView 'hiOpenEditor)
      printf("S3C1E-API %L %L=%L\n" stage fn getd(fn)))
  )
)

s3c1eApi("STARTUP")

; P1/P2: touch a cellview, then try the three documented shapes of dbCreateRect on the shell.
shell = car(errset(dbOpenCellViewByType(LIB "s3c_asg_shell" "schematic" "schematic" "a")))
printf("S3C1E-SHELL opened=%L shapes=%L\n" shell
       car(errset(length(car(errset(shell->shapes))))))
s3c1eApi("AFTER-OPEN")

when(shell
  let((r1 r2 r3 n)
    r1 = errset(dbCreateRect(shell list(list(-2.0 -2.0) list(-1.0 -1.0))))
    r2 = errset(dbCreateRect(shell list(list(-4.0 -4.0) list(-3.0 -3.0)) 'drawing 'analogNet))
    r3 = errset(dbCreateRect(shell list('artifact 'drawing)
                             list(list(-6.0 -6.0) list(-5.0 -5.0))))
    printf("S3C1E-RECT A(points only)=%L B(drawing analogNet)=%L C(artifact drawing)=%L\n"
           car(r1) car(r2) car(r3))
    n = car(errset(length(shell->shapes)))
    printf("S3C1E-SHELL shapes_after=%L\n" n)
    foreach(s shell->shapes
      when(s->objType == "rect"
        printf("S3C1E-RECTFIG lpp=%L bbox=%L\n" car(errset(s->lpp)) car(errset(s->bBox))))
    )
    printf("S3C1E-SAVE %L\n" errset(dbSave(shell)))
    dbClose(shell)
  )
)
s3c1eApi("AFTER-DRAW-ATTEMPT")

; P3: the direction write, on the smallest delivered symbol. Read before, write, read after, save.
sym = car(errset(dbOpenCellViewByType(LIB "sc1_s3b_p33_bank_7" "symbol" "symbol" "a")))
printf("S3C1E-SYM opened=%L terminals=%L shapes=%L\n" sym
       car(errset(length(sym->terminals))) car(errset(length(sym->shapes))))
when(sym
  foreach(termObj sym->terminals
    printf("S3C1E-BEFORE %L dir=%L net=%L\n" termObj->name car(errset(termObj->direction))
           car(errset(if(termObj->net termObj->net->name "-")))))
  ; scan = signal output, bgate = signal input, vscan = supply
  foreach(pair list(list("scan" 'output) list("bgate" 'input) list("vscan" 'inputOutput))
    foreach(termObj sym->terminals
      when(termObj->name == car(pair)
        let((a b after)
          a = errset(dbSetq(termObj->direction nth(1 pair)))
          b = errset(termObj->direction = nth(1 pair))
          after = car(errset(termObj->direction))
          printf("S3C1E-SET %L want=%L dbSetq=%L assign=%L now=%L\n" car(pair) nth(1 pair)
                 car(a) car(b) after)
        )
      )
    )
  )
  foreach(termObj sym->terminals
    printf("S3C1E-AFTER %L dir=%L\n" termObj->name car(errset(termObj->direction))))
  printf("S3C1E-SAVE-SYM %L\n" errset(dbSave(sym)))
  dbClose(sym)
)

; P4: the editor's own check, now that the package may be loaded. Literal errset() form only --
; getd('schCheck) then a call through funcall was measured to misbehave on this build.
sch2 = car(errset(dbOpenCellViewByType(LIB "sc1_s3b_p33_bank_7" "schematic" "schematic" "r")))
when(sch2
  printf("S3C1E-DBCHECK %L\n" errset(dbCheck(sch2)))
  printf("S3C1E-SCHCHECK %L\n" errset(schCheck(sch2)))
  dbClose(sch2)
)
printf("S3C1E_DONE\n")
exit()
