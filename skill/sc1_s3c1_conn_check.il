;; sc1_s3c1_conn_check.il
;;
;; SCAN-1 S3C1 -- per-instance terminal nets, and the editor's own check with the schematic package
;; loaded. Two separate questions the audit asked about, answered from the database:
;;
;;   K lines: which net each instance terminal actually carries IN THE PARENT VIEW. Net names are
;;     per view, so a parent's wire for the bank's bgate pin can legally be named gate33 -- the
;;     cross-view comparison in scripts/sc1_s3c1_geom.py has to use these names, not the child's.
;;   check lines: the real error/warning counts per view after the schematic package is loaded.
;;     Measured earlier in this round: the package is not present at startup but does load once a
;;     schematic view has been opened and one editor call has been attempted, so the check runs
;;     here after that trigger and the counts are printed, not summarised.
;;
;; Read-only: views open with mode "r", nothing is dbSave'd. NEW_SIMULATION_RUNS = 0.

s10Lib   = "microled_scan_s3c"
s10Cells = list("c2mos_dff" "sc1_scan_gate" "sc1_ls_core_r2d" "sc1_ls_c1_r2d"
                "sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_s3b_p33_bank_7"
                "sc1_scan_power_1ch_s3c")

procedure(s10Get(obj nm)
  car(errset(dbGet(obj nm)))
)

procedure(s10Val(v)
  if(v == nil "NONE" v)
)

procedure(s10Open(cell view)
  car(errset(dbOpenCellViewByType(s10Lib cell view
                                  if(view == "schematic" "schematic" nil) "r")))
)

procedure(s10NetsOne(cell)
  let((cv)
    cv = s10Open(cell "schematic")
    when(cv != nil
      foreach(i cv~>instances
        foreach(it i~>instTerms
          printf("S10|K|%L|%L|%L|%L|%L\n" cell i~>name it~>name
                 s10Val(if(it~>net it~>net~>name nil))
                 s10Val(it~>direction))
        )
      )
      dbClose(cv)
    )
  )
)

procedure(s10Check(cell view)
  let((cv res)
    cv = s10Open(cell view)
    when(cv != nil
      res = errset(schCheck(cv))
      printf("S10|C|%L|%L|schCheck=%L\n" cell view res)
      dbClose(cv)
    )
  )
)

printf("S10-BEGIN\n")
foreach(cell s10Cells
  s10NetsOne(cell)
)
printf("S10-NETS-DONE\n")

;; load the schematic editor package: open one schematic in edit mode and attempt one editor call,
;; which is what made schCheck reachable in the direction-writing session
seed = car(errset(dbOpenCellViewByType(s10Lib "c2mos_dff" "schematic" nil "a")))
printf("S10-SEED %L\n" seed != nil)
when(seed != nil
  printf("S10-TOUCH %L\n" car(errset(dbCreateRect(seed))) != nil)
  dbClose(seed)
)
printf("S10-SCHCHECK-FUN %L\n" getd('schCheck) != nil)
printf("S10-SYMCHECK-FUN %L\n" getd('symCheck) != nil)
printf("S10-HICHECK-FUN %L\n" getd('hiCheckAndSave) != nil)

foreach(cell s10Cells
  s10Check(cell "schematic")
  s10Check(cell "symbol")
)
printf("S10-DONE\n")
nil
