; SCH-1 Part D: read the ASG-made schematic back out of OpenAccess, run the database checker over
; it, save it, and re-open it read-only to prove the connectivity survived the save.
;
; Every number printed here is read from the cellview -- this file contains no knowledge of the
; DFF topology, so the connectivity table it emits is generated rather than typed.
;
; Accessor notes, all measured on this build: the SKILL reader rejects the `~` operator at parse
; time, `->` works on db: handles, and dbGet(obj "attr") is the documented form that also accepts
; a computed attribute name. `cv->insts`/`cv->terms` are NOT valid attribute names here -- the
; working ones are "instances"/"nets"/"shapes". A missing RB- line is therefore a finding, not a
; lost run, which is why each read is errset-wrapped (one load-time error aborts the whole file).
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_readback.il 400 RB_DONE
printf("RB-BEGIN\n")
printf("RB-DBCHECK %L\n" getd('dbCheck))
printf("RB-DBSAVE %L\n" getd('dbSave))

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(rbDump(cv tag)
  let((nIns nNets nTerms nShapes)
    nIns = errset(length(dbGet(cv "instances")))
    nNets = errset(length(dbGet(cv "nets")))
    nTerms = errset(length(dbGet(cv "terms")))
    nShapes = errset(length(dbGet(cv "shapes")))
    printf("%s-SUMMARY instances=%L nets=%L terms=%L shapes=%L\n" tag nIns nNets nTerms nShapes)
    foreach(inst dbGet(cv "instances")
      errset(printf("%s-INST %L master=%L/%L:%L model=%L\n" tag dbGet(inst "name")
                     dbGet(inst "libName") dbGet(inst "cellName") dbGet(inst "viewName")
                     dbGet(inst "model")))
      foreach(it dbGet(inst "instTerms")
        errset(printf("%s-CON %L %L %L\n" tag dbGet(inst "name") dbGet(dbGet(it "term") "name")
                       if(dbGet(it "net") dbGet(dbGet(it "net") "name") "UNCONNECTED")))
      )
    )
    foreach(net dbGet(cv "nets")
      errset(printf("%s-NET %L instTermCount=%L\n" tag dbGet(net "name") dbGet(net "instTermCount")))
    )
    foreach(term dbGet(cv "terms")
      errset(printf("%s-TERM %L %L\n" tag dbGet(term "name") dbGet(term "direction")))
    )
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
if(cv errset(printf("RB-OPEN-MODE-a %L\n" cv)) errset(printf("RB-OPEN-MODE-a nil\n")))
when(cv
  printf("RB-OPENED-WRITABLE\n")
  rbDump(cv "PRE")
  errset(printf("RB-CHECK-RESULT %L\n" dbCheck(cv)))
  errset(printf("RB-SAVE-RESULT %L\n" dbSave(cv)))
  dbClose(cv)
  printf("RB-CLOSED-AFTER-SAVE\n")
)
cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv2
  printf("RB-REOPENED-READ-ONLY\n")
  rbDump(cv2 "POST")
  dbClose(cv2)
,
  printf("RB-REOPEN-FAILED\n")
)
printf("RB_DONE\n")
exit()
