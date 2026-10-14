;; sc1_libcheck.il -- does the library map the desktop shortcut actually uses resolve microled_scan_s3c?
;;
;; Why this is a separate check and not a reuse of scripts/sc1_s3c_run_oa.sh: that runner starts a
;; session whose cwd is s3c_oa with an isolated HOME on purpose, so it reads
;; s3c_oa/cds.lib and proves only the isolated session can see the library. The desktop entry runs
;; cadence_work/launch_virtuoso.sh, which does `cd $WORK` and `exec virtuoso` with no -cdslib flag,
;; i.e. the session resolves $WORK/cds.lib with the real HOME. This file has to be loaded by a
;; session started the same way, otherwise "visible" would mean the wrong thing.
;;
;; Printed per run: HOME, cwd, whether the lib object exists, its cell count, then every one of the
;; eight design cells with schematic and symbol view identity read-only from the OA. Read-only: no
;; dbSave, no writes, NEW_SIMULATION_RUNS = 0.

lcLib = "microled_scan_s3c"
lcTop = "sc1_scan_power_1ch_s3c"
lcCells = list("c2mos_dff" "sc1_scan_gate" "sc1_ls_core_r2d" "sc1_ls_c1_r2d"
               "sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_s3b_p33_bank_7"
               "sc1_scan_power_1ch_s3c")

procedure(lcVal(v) if(v v "NONE"))
procedure(lcLen(x) if(x length(x) -1))

procedure(lcView(cell view)
  let((cv)
    cv = car(errset(dbOpenCellViewByType(lcLib cell view nil "r")))
    printf("LC-VIEW %L %L opened=%L cellviewName=%L lib=%L shapes=%L instances=%L terminals=%L\n"
           cell view lcVal(cv != nil) lcVal(if(cv cv~>name nil))
           lcVal(if(cv cv~>cellView~>libName nil)) lcLen(if(cv cv~>shapes nil))
           lcLen(if(cv cv~>instances nil)) lcLen(if(cv cv~>terminals nil)))
    errset(dbClose(cv))
    cv != nil
  )
)

;; measured in this build: `getenv` is not a SKILL function ("*Error* eval: undefined function -
;; getenv"), the accessor is getshellenv, and it is wrapped so a missing attribute can never abort the
;; check before the verdict line is printed
printf("LC-BEGIN home=%L pwd=%L\n" car(errset(getshellenv("HOME"))) car(errset(getshellenv("PWD"))))
lib = ddGetObj(lcLib)
printf("LC-LIB %L obj=%L cells=%L\n" lcLib lcVal(lib != nil) lcLen(if(lib lib~>cells nil)))
when(lib
  printf("LC-LIBPATH %L\n" lcVal(car(errset(lib~>paths))))
  foreach(cell lcCells
    printf("LC-CELL %L\n" cell)
    lcView(cell "schematic")
    lcView(cell "symbol")
  )
  printf("LC-TOP %L schematic=%L\n" lcTop lcView(lcTop "schematic"))
  printf("LC-TOP %L symbol=%L\n" lcTop lcView(lcTop "symbol"))
)
unless(lib printf("LC-LIB-NOT-RESOLVING %L -- the cds.lib this session read has no such DEFINE\n" lcLib))
printf("LC-DONE resolved=%L\n" lcVal(lib != nil))
nil
