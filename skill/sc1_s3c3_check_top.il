;; sc1_s3c3_check_top.il
;;
;; Section 3 allows the top view one Check and Save to refresh its check state, and forbids re-laying
;; its already-correct 11/11 wiring. So this opens sc1_scan_power_1ch_s3c:schematic writable, draws
;; and deletes nothing, runs schCheck, prints what the checker extracted, and saves only when the
;; error count is zero. The child views are opened read-only beforehand to record their state.
;; NEW_SIMULATION_RUNS = 0.

ctLib = "microled_scan_s3c"
ctTop = "sc1_scan_power_1ch_s3c"

procedure(ctVal(v) if(v v "NONE"))

procedure(ctDump(cv, view)
  let((i tm f)
    foreach(i cv~>instances
      foreach(tm i~>instTerms
        printf("CT-X %L %L %L net=%L\n" view i~>name ctVal(tm~>name)
               ctVal(if(tm~>net tm~>net~>name nil)))
      )
    )
    foreach(f cv~>shapes
      when(and(ctVal(f~>layerName) equal(f~>layerName "wire"))
        printf("CT-WIRE %L objType=%L net=%L points=%L\n" view f~>objType
               ctVal(if(f~>net f~>net~>name nil)) f~>points)
      )
    )
  )
)

printf("CT-BEGIN\n")
ro = car(errset(dbOpenCellViewByType(ctLib ctTop "schematic" nil "r")))
printf("CT-READONLY opened=%L shapes=%L insts=%L nets=%L terminals=%L\n" ro != nil
       length(ro~>shapes) length(ro~>instances) length(ro~>nets) length(ro~>terminals))
ctDump(ro ctTop)
dbClose(ro)

cv = car(errset(dbOpenCellViewByType(ctLib ctTop "schematic" nil "a")))
printf("CT-OPEN writable=%L shapes=%L\n" cv != nil length(cv~>shapes))
printf("CT-API-before-schCheck=%L\n" if(getd('schCheck) "EXISTS" "NIL"))
res = errset(schCheck(cv))
pair = if(res nth(0 res) nil)
errs = -1
warns = -1
when(and(pair listp(pair))
  errs = car(pair)
  warns = if(cdr(pair) car(cdr(pair)) -1)
)
printf("CT-CHECK errors=%L warnings=%L raw=%L\n" errs warns ctVal(res))
ctDump(cv ctTop)
saved = nil
when(and(res != nil equal(errs 0) cv)
  saved = car(errset(dbSave(cv)))
  printf("CT-SAVE rc=%L\n" ctVal(saved))
)
printf("CT-VERDICT %L errors=%L warnings=%L saved=%L\n" ctTop errs warns ctVal(saved != nil))
when(cv dbClose(cv))
printf("CT-END\n")
nil
