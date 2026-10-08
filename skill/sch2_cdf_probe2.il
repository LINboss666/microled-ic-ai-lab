; SCH-2 Part C, probe 2: reach the PDK master and read the CDF parameter dictionary it really uses.
;
; Read-only. The vendor master is inspected, never evaluated: no CDF callback and no
; dbEvalParamCell/dbCheckParamCell call is made against a PDK object, because those would write
; into the vendor library.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch2_cdf_probe2.il 600 CE_DONE
printf("CE-BEGIN\n")
ddCell = car(errset(ddGetObj("smic18mmrf" "n18")))
printf("CE-DDGETOBJ %L name=%L\n" ddCell car(errset(ddGetObjName(ddCell))))

; --- how the vendor symbol view can be reached from a batch session
v1 = car(errset(dbOpenCellViewByType("smic18mmrf" "n18" "symbol" "symbol" "r")))
v2 = car(errset(dbOpenCellViewByType("smic18mmrf" "n18" "symbol" nil "r")))
v3 = car(errset(dbOpenCellViewByType("smic18mmrf" "n18" "layout" nil "r")))
printf("CE-OPEN symbol/symbol=%L symbol/nil=%L layout/nil=%L\n" v1 v2 v3)

; --- CDF dictionaries reachable without opening the view
base = car(errset(cdfGetBaseCellCDF(ddCell)))
eff = car(errset(cdfGetCellCDF(ddCell)))
user = car(errset(cdfGetUserCellCDF(ddCell)))
printf("CE-CDF base=%L effective=%L user=%L\n" base eff user)

PNAMES = list("l" "w" "fw" "wf" "m" "mult" "fingers" "area" "model" "nws")

printf("CE-SECTION BASE-CDF\n")
foreach(pn PNAMES
  pp = car(errset(cdfFindParamByName(base pn)))
  printf("CE-BASE %L found=%L value=%L default=%L type=%L units=%L form=%L\n" pn
         if(pp "yes" "no") car(errset(dbGet(pp "value"))) car(errset(dbGet(pp "defaultValue")))
         car(errset(dbGet(pp "type"))) car(errset(dbGet(pp "units"))) car(errset(dbGet(pp "form"))))
)

printf("CE-SECTION EFFECTIVE-CDF\n")
foreach(pn PNAMES
  pp = car(errset(cdfFindParamByName(eff pn)))
  printf("CE-EFF %L found=%L value=%L type=%L units=%L prompt=%L\n" pn
         if(pp "yes" "no") car(errset(dbGet(pp "value"))) car(errset(dbGet(pp "type")))
         car(errset(dbGet(pp "units"))) car(errset(dbGet(pp "prompt"))))
)

; --- what the CDF object itself exposes (attribute discovery)
foreach(a list("objType" "name" "cellName" "libName" "parameters" "cdfParameters" "paramList")
  printf("CE-CDFATTR %L => %L\n" a car(errset(dbGet(base a))))
)

; --- the instance-level CDF, which is what the GUI editor reads for the property sheet
cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv
  inst = car(dbGet(cv "instances"))
  ic = car(errset(cdfGetInstCDF(inst)))
  printf("CE-INSTCDF %L for inst=%L\n" ic dbGet(inst "name"))
  foreach(pn PNAMES
    pp = car(errset(cdfFindParamByName(ic pn)))
    printf("CE-IPARAM %L found=%L value=%L type=%L units=%L\n" pn
           if(pp "yes" "no") car(errset(dbGet(pp "value"))) car(errset(dbGet(pp "type")))
           car(errset(dbGet(pp "units"))))
  )
  dbClose(cv)
)
printf("CE_DONE\n")
exit()
