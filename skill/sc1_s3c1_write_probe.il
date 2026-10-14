; SCAN-1 S3-C1 section 2/4: the one small WRITE test the task book asks for, done on the importer
; shell cell rather than on a delivered object.
;
; Why s3c_asg_shell: it is the file-scope wrapper spiceIn needed (SPICEIN-77), it is not one of the
; eight delivered cells, it is inside this task's own library, and it already carries nine real
; terminals with pins and pin labels -- the same port set as the formal top. So it can answer the
; three open questions without risking anything that is being reviewed:
;   W1 can a terminal's logical direction be set and kept (and which of the two forms works)?
;   W2 can an existing figure (a pin label) be moved and does its bbox show the move?
;   W3 can a new graphic (a rect) be created in a batch session at all?
;
; Nothing here touches a delivered cell, the PDK or any pre-existing library. dbDeleteObj is nil on
; this build, so the test rectangle stays in the shell cell and that is recorded rather than hidden.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_write_probe.il 600 S3C1W_DONE
printf("S3C1W-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
CELL = car(errset(getShellEnvVar("S3C_WCELL")))
CELL = if(CELL CELL "s3c_asg_shell")
WANT = list(list("d" 'input) list("clk" 'input) list("blank" 'input) list("core_ok33" 'input)
           list("scan" 'output) list("vdd18" 'inputOutput) list("vdd33" 'inputOutput)
           list("vscan" 'inputOutput) list("vss" 'inputOutput))

printf("S3C1W-CELL %L\n" CELL)
cv = car(errset(dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")))
unless(cv printf("S3C1W-OPEN-FAILED\n"))
when(cv
  printf("S3C1W-OPENED terminals=%L shapes=%L\n" car(errset(length(cv->terminals)))
         car(errset(length(cv->shapes))))
  foreach(pair WANT
    termObj = nil
    foreach(termObjX cv->terminals when(termObjX->name == car(pair) termObj = termObjX))
    if(termObj == nil
      printf("S3C1W-MISSING-TERMINAL %L\n" car(pair))
      let((before a b after)
        before = car(errset(termObj->direction))
        a = errset(dbSetq(termObj->direction nth(1 pair)))
        b = errset(let((x) x = nth(1 pair) termObj->direction = x))
        after = car(errset(termObj->direction))
        printf("S3C1W-DIR %L before=%L dbSetq=%L assign=%L after=%L want=%L\n" car(pair) before
               car(a) car(b) after nth(1 pair))
      )
    )
  )
  ; W2: move one pin label by half a micron and read the bounding box back
  lbl = car(errset(cv->shapes))
  moved = nil
  foreach(s cv->shapes
    when(and(s->objType == "textDisplay" moved == nil)
      let((bb r)
        bb = car(errset(s->bBox))
        r = errset(dbMoveFig(s list(0.0 0.0) list(500n 500n)))
        printf("S3C1W-MOVE objType=%L lpp=%L bbox_before=%L result=%L bbox_after=%L\n"
               s->objType car(errset(s->lpp)) bb car(r) car(errset(s->bBox)))
        moved = s
      )
    )
  )
  unless(moved printf("S3C1W-MOVE-SKIP no textDisplay shape found\n"))
  ; W3: create a rectangle on the artifact layer
  let((r f)
    r = errset(dbCreateRect(cv list('artifact 'drawing) list(list(-1.0 -1.0) list(1.0 1.0))))
    f = car(r)
    printf("S3C1W-RECT result=%L objType=%L lpp=%L bbox=%L shapes_now=%L\n" car(r)
           car(errset(f->objType)) car(errset(f->lpp)) car(errset(f->bBox))
           car(errset(length(cv->shapes))))
  )
  printf("S3C1W-SAVE %L\n" errset(dbSave(cv)))
  dbClose(cv)
)

; re-open read-only inside the same session: what survived the save?
cv2 = car(errset(dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")))
when(cv2
  foreach(termObj2 cv2->terminals
    printf("S3C1W-REOPEN-TERM %L dir=%L net=%L\n" termObj2->name car(errset(termObj2->direction))
           car(errset(if(termObj2->net termObj2->net->name "-")))))
  printf("S3C1W-REOPEN shapes=%L\n" car(errset(length(cv2->shapes))))
  dbClose(cv2)
)
printf("S3C1W_DONE\n")
exit()
