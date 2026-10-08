; SCH-2 Part C: find, read-only, what the teacher PDK really calls a MOS parameter and which
; batch API can write it. Nothing in this file saves anything, and no evaluation or callback is
; invoked against a PDK object: the vendor master is opened read-only and inspected.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch2_cdf_probe.il 500 CD_DONE
printf("CD-BEGIN\n")
foreach(f list('dbReplaceInstParamList 'dbResetPropList 'dbCreateProp 'dbDeleteObject
               'cdfUpdateInstParam 'cdfUpdateInstSingleParam 'cdfSyncInstParamValue
               'cdfFindParamByName 'cdfGetBaseCellCDF 'cdfGetCellCDF 'cdfGetUserCellCDF
               'cdfParseFloatString 'cdfFormatFloatString 'dbGetPropByName 'dbSetPropValue)
  printf("CD-FN %L => %L\n" f getd(f))
)
printf("CD-PARSE ln => %L\n" cdfParseFloatString("ln"))
printf("CD-PARSE 2u => %L\n" cdfParseFloatString("2u"))
printf("CD-PARSE 2e-6 => %L\n" cdfParseFloatString("2e-6"))
printf("CD-PARSE 220n => %L\n" cdfParseFloatString("220n"))

procedure(cdAttrs(obj tag)
  let((vv)
    foreach(a list("objType" "name" "cellName" "libName" "parameters" "paramList" "formParameters"
                   "callbackData" "viewName" "isPcell" "cellView" "props")
      vv = car(errset(dbGet(obj a)))
      if(vv == nil printf("CD-ATTR %L %L => nil\n" tag a) printf("CD-ATTR %L %L => %L\n" tag a vv))
    )
    foreach(a list("objType" "name" "parameters" "paramDefinitions" "cdfType" "cell")
      vv = car(errset(getattr2(obj a)))
      printf("CD-ATTR2 %L %L => %L\n" tag a vv)
    )
  )
)

foreach(pair list(list("smic18mmrf" "n18") list("smic18mmrf" "p18"))
  printf("CD-MASTER %L/%L\n" car(pair) cadr(pair))
  cvs = errset(dbGetCellViewList(ddGetObj(car(pair)) cadr(pair)))
  printf("CD-VIEWS %L\n" cvs)
  cvw = dbOpenCellViewByType(car(pair) cadr(pair) "symbol" "symbol" "r")
  when(cvw
    cdAttrs(cvw "MASTER-CV")
    cdfb = errset(cdfGetBaseCellCDF(dbGet(cvw "cell")))
    printf("CD-BASECDF %L\n" cdfb)
    cdfe = errset(cdfGetCellCDF(dbGet(cvw "cell")))
    printf("CD-EFFECTIVECDF %L\n" cdfe)
    dbClose(cvw)
  )
)

; the CDF object itself is the parameter dictionary: list what it holds
cv2 = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv2
  i0 = car(dbGet(cv2 "instances"))
  instcdf = errset(cdfGetInstCDF(i0))
  printf("CD-INSTCDF %L for %L\n" instcdf dbGet(i0 "name"))
  cdAttrs(car(instdcdf) "INSTCDF")
  foreach(nm list("l" "w" "fw" "wf" "m" "fingers" "mult" "area")
    pp = car(errset(cdfFindParamByName(car(instdcdf) nm)))
    if(pp
      printf("CD-PARAM %L found objType=%L name=%L value=%L type=%L units=%L prompt=%L\n" nm
             car(errset(dbGet(pp "objType"))) car(errset(dbGet(pp "name")))
             car(errset(dbGet(pp "value"))) car(errset(dbGet(pp "type")))
             car(errset(dbGet(pp "units"))) car(errset(dbGet(pp "prompt"))))
    ,
      printf("CD-PARAM %L ABSENT\n" nm)
    )
  )
  dbClose(cv2)
)
printf("CD_DONE\n")
exit()
