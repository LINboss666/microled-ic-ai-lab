;; sc1_s3c4_check_parents.il -- leaf-to-root Check and Save for the three schematics that draw the
;; repaired Symbols, with no rewiring of any kind.
;;
;; The S3C4 task book allows exactly this: after the Symbol text was moved, the parent schematics
;; carry "update time" markers, and a Check and Save clears them. It forbids using that pass to
;; re-route, so nothing here creates, deletes or moves a figure: each view is opened read-only and its
;; instance terminals, nets and wire points are printed; the same view is then opened writable,
;; schCheck runs, the identical dump is printed again, and dbSave happens ONLY when the error count is
;; zero. The two dumps plus scripts/sc1_s3c3_verify.py are what proves 39/39 pin attachment and 23/23
;; external port attachment survived the pass unchanged. NEW_SIMULATION_RUNS = 0.

cpLib = "microled_scan_s3c"
cpViews = list("sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_scan_power_1ch_s3c")

procedure(cpVal(v) if(v v "NONE"))

procedure(cpDump(cv, view, tag)
  let((i tm f)
    printf("%L %L shapes=%L insts=%L nets=%L terminals=%L\n" tag view length(cv~>shapes)
           length(cv~>instances) length(cv~>nets) length(cv~>terminals))
    foreach(i cv~>instances
      foreach(tm i~>instTerms
        printf("%L-ITERM %L %L %L net=%L dir=%L\n" tag view i~>name cpValx(tm~>name)
               cpVal(if(tm~>net tm~>net~>name nil)) cpVal(tm~>direction))
      )
    )
    foreach(f cv~>shapes
      when(and(cpVal(f~>layerName) equal(f~>layerName "wire"))
        printf("%L-WIRE %L objType=%L net=%L points=%L\n" tag view f~>objType
               cpVal(if(f~>net f~>net~>name nil)) f~>points)
      )
    )
    foreach(f cv~>shapes
      when(and(cpVal(f~>layerName) equal(f~>layerName "pin"))
             or(equal(f~>objType "label") equal(f~>objType "textDisplay"))
        printf("%L-PINTEXT %L text=%L xy=%L\n" tag view cpVal(dbGet(f 'theLabel)) cpVal(f~>xy))
      )
    )
  )
)

procedure(cpValx(v) if(v v "NONE"))

printf("CP-BEGIN views=%L\n" length(cpViews))
foreach(view cpViews
  ro = car(errset(dbOpenCellViewByType(cpLib view "schematic" nil "r")))
  printf("CP-RO-OPEN %L opened=%L\n" view cpVal(ro != nil))
  cpDump(ro view "CP-BEFORE")
  errset(dbClose(ro))
  cv = car(errset(dbOpenCellViewByType(cpLib view "schematic" nil "a")))
  printf("CP-RW-OPEN %L writable=%L\n" view cpVal(cv != nil))
  res = errset(schCheck(cv))
  pair = if(res nth(0 res) nil)
  errs = -1
  warns = -1
  when(and(res listp(pair))
    errs = car(pair)
    warns = if(cdr(pair) car(cdr(pair)) -1)
  )
  printf("CP-CHECK %L errors=%L warnings=%L raw=%L\n" view errs warns cpVal(res))
  cpDump(cv view "CP-AFTER")
  saved = nil
  when(and(res != nil equal(errs 0) cv)
    saved = car(errset(dbSave(cv)))
  )
  printf("CP-VERDICT %L errors=%L warnings=%L saved=%L\n" view errs warns cpVal(saved != nil))
  errset(dbClose(cv))
)
printf("CP-END\n")
nil
