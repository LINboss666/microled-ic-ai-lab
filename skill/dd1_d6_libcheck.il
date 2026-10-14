;; dd1_d6_libcheck.il -- does the library map the desktop shortcut actually uses resolve
;; microled_data_d6?
;;
;; Copy-by-value of skill/sc1_libcheck.il (which is not modified) with this task's library, top and
;; eight cells. Same reasoning: scripts/dd1_d6_run_oa.sh starts a session whose cwd is data_d6_oa
;; with an isolated HOME, so it reads data_d6_oa/cds.lib and only proves the isolated session sees
;; the library. The desktop entry runs cadence_work/launch_virtuoso.sh, which does `cd $WORK` and
;; `exec virtuoso` with no -cdslib flag, so it resolves $WORK/cds.lib with the real HOME. This file
;; has to be loaded by a session started the same way, otherwise "visible" would mean the wrong thing.
;;
;; Read-only: every view is opened mode "r", there is no dbSave and no new simulation run.

lcLib = "microled_data_d6"
lcTop = "dd1_data_top_1ch"
lcCells = list("c2mos_dff" "sc1_scan_gate" "dd1_inv18" "dd1_control_1ch" "data_sink_1ch"
               "data_bias_ref" "dd1_sink_unit_1ch" "dd1_data_top_1ch")

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
