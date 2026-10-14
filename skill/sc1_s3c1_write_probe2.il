; SCAN-1 S3-C1 section 2: the second write test, corrected against what the first one revealed.
;
; Two mistakes in the previous probe are fixed here and both came from the probe, not from the data:
;   * the symbol view was opened as dbOpenCellViewByType(lib cell "symbol" "symbol" "a") and that
;     returned nil, so no direction was ever attempted. The view TYPE of a symbol cellview is not
;     the string "symbol" on this build -- the working form (used by the read-back) passes nil for
;     the type and lets the name select the view.
;   * every dbCreateRect call was wrapped in errset, which turned a real error into a silent nil and
;     lost the message. The drawing calls below are made WITHOUT errset so that whatever the build
;     complains about is written into the log, with a marker line before and after each one.
;
; What is decided here and used everywhere afterwards:
;   D1 can a terminal direction be set, and does it survive dbSave (checked in a fresh session)?
;   D2 is dbMoveFig reversible -- move one pin label by a delta and then by the negated delta, so
;       the delivered object ends where it started while the bbox proves both moves acted.
;   D3 which graphic-creation entry point, if any, works in a batch session.
;
; Writes are confined to this task's own library and to one cell (sc1_s3b_p33_bank_7) whose full
; state is archived in backup_microled_scan_s3c_pre_s3c1_20261014.tgz. The PDK is never opened for
; write. Nothing outside the eight symbols/schematics and the shell is touched.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_write_probe2.il 700 S3C1W2_DONE
printf("S3C1W2-BEGIN\n")
LIB = "microled_scan_s3c"
CELL = "sc1_s3b_p33_bank_7"

procedure(s3c1w2FindTerm(cv name)
  let((found)
    found = nil
    foreach(termObj cv->terminals when(termObj->name == name found = termObj))
    found
  )
)

; ---- D1 direction, on the symbol view opened the way the read-back opens it
sym = car(errset(dbOpenCellViewByType(LIB CELL "symbol" nil "a")))
printf("S3C1W2-SYM opened=%L terminals=%L shapes=%L\n" sym
       car(errset(length(sym->terminals))) car(errset(length(sym->shapes))))
when(sym
  foreach(termObj sym->terminals
    printf("S3C1W2-BEFORE %L dir=%L\n" termObj->name car(errset(termObj->direction))))
  want = list(list("scan" 'output) list("bgate" 'input) list("vscan" 'inputOutput))
  foreach(pair want
    termObj = s3c1w2FindTerm(sym car(pair))
    if(termObj == nil
      printf("S3C1W2-MISSING %L\n" car(pair))
      let((a b mid)
        a = errset(dbSetq(termObj->direction nth(1 pair)))
        mid = car(errset(termObj->direction))
        b = errset(termObj->direction = nth(1 pair))
        printf("S3C1W2-SET %L want=%L after_dbSetq=%L dbSetq_result=%L assign_result=%L now=%L\n"
               car(pair) nth(1 pair) mid car(a) car(b) car(errset(termObj->direction)))
      )
    )
  )
  printf("S3C1W2-SAVE %L\n" errset(dbSave(sym)))
  dbClose(sym)

  ; ---- D2 dbMoveFig reversibility on one pin label of the same symbol
  re = car(errset(dbOpenCellViewByType(LIB CELL "symbol" nil "a")))
  when(re
    target = nil
    foreach(s re->shapes
      when(and(target == nil s->objType == "textDisplay") target = s))
    if(target == nil
      printf("S3C1W2-MOVE-SKIP no textDisplay in the symbol\n")
      let((bb0 r1 bb1 r2 bb2)
        bb0 = car(errset(target->bBox))
        r1 = errset(dbMoveFig(target list(0.0 0.0) list(500n 500n)))
        bb1 = car(errset(target->bBox))
        r2 = errset(dbMoveFig(target list(0.0 0.0) list(-500n -500n)))
        bb2 = car(errset(target->bBox))
        printf("S3C1W2-MOVE bbox0=%L move_out=%L bbox1=%L move_back=%L bbox2=%L same_as_start=%L\n"
               bb0 car(r1) bb1 car(r2) bb2 (bb0 == bb2))
        printf("S3C1W2-SAVE2 %L\n" errset(dbSave(re)))
      )
    )
    dbClose(re)
  )
)

; ---- D3 drawing, called bare so the log keeps the real message
printf("S3C1W2_DONE\n")
let((dummy)
  printf("S3C1W2-DRAW-BEGIN (no errset: an error stops this block and the log carries it)\n")
  sh = car(errset(dbOpenCellViewByType(LIB "s3c_asg_shell" "schematic" "schematic" "a")))
  printf("S3C1W2-DRAW-SHELL opened=%L shapes=%L\n" sh car(errset(length(sh->shapes))))
  when(sh
    printf("S3C1W2-DRAW-TRY dbCreateRect(points only)\n")
    f1 = dbCreateRect(sh list(list(-2.0 -2.0) list(-1.0 -1.0)))
    printf("S3C1W2-DRAW-RESULT1 %L objType=%L\n" f1 car(errset(f1->objType)))
    printf("S3C1W2-DRAW-TRY dbCreateRect(points objType lpp)\n")
    f2 = dbCreateRect(sh list(list(-4.0 -4.0) list(-3.0 -3.0)) 'rect 'artifact)
    printf("S3C1W2-DRAW-RESULT2 %L objType=%L\n" f2 car(errset(f2->objType)))
    printf("S3C1W2-DRAW-TRY dbCreateLine(lpp points)\n")
    f3 = dbCreateLine(sh list('artifact 'drawing) list(list(-6.0 -6.0) list(-5.0 -5.0)) 0.1)
    printf("S3C1W2-DRAW-RESULT3 %L objType=%L\n" f3 car(errset(f3->objType)))
    printf("S3C1W2-DRAW-TRY dbCreateLabel(lpp points text)\n")
    f4 = dbCreateLabel(sh list('artifact 'drawing) list(0.0 0.0) "s3c1w2" 'center 'center 0.5)
    printf("S3C1W2-DRAW-RESULT4 %L objType=%L\n" f4 car(errset(f4->objType)))
    printf("S3C1W2-DRAW-SHELL shapes_now=%L\n" car(errset(length(sh->shapes))))
    errset(dbSave(sh))
    dbClose(sh)
  )
)
printf("S3C1W2_DRAW_END\n")
exit()
