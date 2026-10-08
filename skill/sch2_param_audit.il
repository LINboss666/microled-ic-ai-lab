; SCH-2 Part B: read every parameter layer the database can actually show, for the four devices the
; operator named plus a full sweep of all 18 MOS. Strictly read only: the source cellview is opened
; with mode "r", nothing is saved, and no evaluation call (dbEvalParamCell / dbCheckParamCell /
; CDF callbacks) is made against the PDK masters -- those would write into the vendor library.
;
; Layers captured here:
;   OA instance property   -> dbFindProp(inst "<name>") value + type, over a candidate name list
;   OA instance parameter  -> the "parameters" attribute of the instance and of its master
;   master identity        -> lib/cell/view + whether the master is a non-SKILL PCell
;   physical evidence      -> the instance bounding box, which follows the evaluated geometry
; Anything absent prints ABSENT, so a missing layer is visible instead of silently zero.
;
; Run: SCH1_CELL=c2mos_dff_1bit bash scripts/sch_virtuoso.sh skill/sch2_param_audit.il 500 PA_DONE
printf("PA-BEGIN\n")
foreach(f list('cdfGetInstCDF 'cdfGetObjParam 'cdfGetParamValue 'cdfSetParamValue 'pcxDisplayParams
               'dbGetParamList 'dbGetParamValue 'dbSetParamValue 'dbEvalParamCell 'dbCheckParamCell
               'dbIsNonSKILLPcell 'dbGetCellProperties 'dbPropList 'schCheck 'hiCheckAndSave 'asiNetlist)
  printf("PA-FN %L => %L\n" f getd(f))
)

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")
NAMES = list("l" "w" "fw" "wf" "Wfg" "fingers" "m" "mult" "model" "simW" "simL"
             "area" "periphery" "as" "ad" "ps" "nws" "nwelltap")
FOCUS = list("mn_c" "mn_k2" "mp_c" "mp_k2")

procedure(paProp(inst nm)
  let((pp val typ)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp
      list(nm car(errset(dbGet(pp "value"))) car(errset(dbGet(pp "type"))))
    ,
      list(nm "ABSENT" "ABSENT")
    )
  )
)

procedure(paInst(cv nm)
  let((found)
    found = nil
    foreach(obj dbGet(cv "instances")
      if(dbGet(obj "name") == nm found = obj)
    )
    found
  )
)

procedure(paReport(cv inst why)
  let((master bb)
    master = dbGet(inst "master")
    printf("PA-INST %L why=%L master=%L/%L:%L model=%L objType=%L\n" dbGet(inst "name") why
           dbGet(master "libName") dbGet(master "cellName") dbGet(master "viewName")
           dbGet(inst "model") dbGet(master "objType"))
    printf("PA-MASTER-ISCALLED %L\n" car(errset(dbIsNonSKILLPcell(master))))
    printf("PA-MASTER-VIEW-PARAMETERS %L\n" car(errset(dbGet(master "parameters"))))
    printf("PA-MASTER-CELL-PARAMETERS %L\n" car(errset(dbGet(dbGet(master "cell") "parameters"))))
    printf("PA-INST-PARAMETERS %L\n" car(errset(dbGet(inst "parameters"))))
    printf("PA-INST-PROPLIST %L\n" car(errset(dbGet(inst "propList"))))
    printf("PA-INST-OBJTYPE %L\n" dbGet(inst "objType"))
    bb = car(errset(dbGet(inst "bBox")))
    printf("PA-INST-BBOX %L\n" bb)
    printf("PA-INST-CDF %L\n" car(errset(cdfGetInstCDF(inst))))
    foreach(nm NAMES
      r = paProp(inst nm)
      unless(r == nil
        printf("PA-PROP %L %L value=%L type=%L\n" dbGet(inst "name") car(r) cadr(r) caddr(r))
      )
    )
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
unless(cv
  printf("PA-OPEN-FAILED\n")
)
when(cv
  printf("PA-CELL %L/%L instances=%L nets=%L\n" LIB CELL length(dbGet(cv "instances"))
         length(dbGet(cv "nets")))
  foreach(nm FOCUS
    i = paInst(cv nm)
    if(i paReport(cv i "operator_named") printf("PA-INST-NOT-FOUND %L\n" nm))
  )
  printf("PA-FULL-SWEEP-BEGIN\n")
  foreach(inst dbGet(cv "instances")
    when(dbGet(inst "model")
      printf("PA-SWEEP %L %L %L %L\n" dbGet(inst "name") dbGet(inst "model")
             car(errset(dbGet(car(errset(dbFindProp(inst "l"))) "value")))
             car(errset(dbGet(car(errset(dbFindProp(inst "simW"))) "value"))))
    )
  )
  printf("PA-FULL-SWEEP-END\n")
  dbClose(cv)
)
printf("PA_DONE\n")
exit()
