; SCAN_UNIT_TEAM_BEAUTIFY: one read-only session that answers two acceptance questions at once.
;
;   1) do all 16 delivered views resolve from the library map the DESKTOP SHORTCUT reads, and
;   2) what does the editor's own check say about each schematic, leaf first then parents.
;
; Why its own session: the batch writers run with cwd=cadence_work/s3c_oa against an isolated map,
; so they can only prove the isolated session sees the library. Cadence resolves cds.lib from the
; working directory and the shortcut's launcher does `cd $WORK` with no -cdslib, so visibility has
; to be tested exactly the way the shortcut starts -- which is what scripts/sch_virtuoso.sh does.
;
; Why leaf-first order: connectivity of a parent depends on its children's symbols, so checking a
; parent before its leaves would report inherited noise as if it were the parent's own.
;
; Read-only. Views open with mode "r"; nothing is saved, no write lock is taken, no figure touched.
; Loop variables are plain globals because this file's earlier let()-bound version aborted with an
; unbound loop variable in this build.
; Run: bash scripts/sch_virtuoso.sh <this file under PROJ> 400 LIBVIS_DONE
printf("LIBVIS-BEGIN\n")
LIB = "sc1_s3c_team_pretty"
printf("LIBVIS-ENV cwd=%L\n" car(errset(getShellEnvVar("PWD"))))
printf("LIBVIS-LIBHANDLE %L\n" car(errset(ddGetObj(LIB))))
CELLS = list("c2mos_dff" "sc1_scan_gate" "sc1_ls_core_r2d" "sc1_ls_c1_r2d"
             "sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_s3b_p33_bank_7" "sc1_scan_power_1ch_s3c")
views = 0
foreach(CL CELLS
  sv = car(errset(dbOpenCellViewByType(LIB CL "schematic" "schematic" "r")))
  yv = car(errset(dbOpenCellViewByType(LIB CL "symbol" nil "r")))
  scount = if(sv car(errset(length(dbGet(sv "shapes")))) 0)
  ycount = if(yv car(errset(length(yv->terminals))) 0)
  schck = if(sv car(errset(schCheck(sv))) "NO-SCHCHECK")
  dbchk = if(sv car(errset(dbCheck(sv))) "NO-DBCHECK")
  printf("LIBVIS-CELL %L schematic=%L shapes=%L symbol=%L symTerms=%L dbCheck=%L schCheck=%L\n" CL if(sv "OPEN" "FAILED") scount if(yv "OPEN" "FAILED") ycount dbchk schck)
  when(sv
    dbClose(sv)
    views = views + 1
  )
  when(yv
    dbClose(yv)
    views = views + 1
  )
)
printf("LIBVIS-SUMMARY views_opened=%L of 16\n" views)
if(views == 16 printf("LIBVIS: PASS every delivered view resolves from the shortcut's library map\n"))
when(views != 16 printf("LIBVIS: FAIL only %L of 16 views resolved\n" views))
printf("LIBVIS_DONE\n")
exit()
