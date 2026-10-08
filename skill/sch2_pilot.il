; SCH-2 Part E pilot: which write reaches the PDK CDF, and what survives a save.
;
; Measured before this pilot: the golden width sits in an OA property named simW, which the PDK CDF
; does not know at all (its parameters are l, w, fw, m, fingers, model), and the instance parameter
; l holds the text "ln", which cdfParseFloatString() cannot turn into a number. A first run of this
; pilot also showed cdfUpdateInstParam() removing properties, which is exactly the hazard the task
; warns about, so the mechanisms are now applied one at a time on a single instance and read back
; three ways after each step: the CDF dictionary, the raw OA properties, and inst->parameters,
; followed by a save plus read-only reopen so the persisted representation is what is judged.
;
; The cell used is a copy (c2mos_dff_1bit_paramfix). c2mos_dff_1bit and the backup are not opened
; for writing anywhere in this file.
;
; Run: SCH1_CELL=c2mos_dff_1bit_paramfix bash scripts/sch_virtuoso.sh skill/sch2_pilot.il 600 PL_DONE
printf("PL-BEGIN\n")
LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit_paramfix")

procedure(plCDFVal(ic pn)
  let((pp)
    pp = car(errset(cdfFindParamByName(ic pn)))
    if(pp car(errset(pp->value)) "NO-SUCH-CDF-PARAM")
  )
)

procedure(plProp(inst pn)
  let((pp)
    pp = car(errset(dbFindProp(inst pn)))
    if(pp car(errset(dbGet(pp "value"))) "ABSENT")
  )
)

procedure(plRead(inst tag)
  let((ic)
    ic = car(errset(cdfGetInstCDF(inst)))
    printf("PL-CDF %L w=%L fw=%L l=%L m=%L fingers=%L model=%L\n" tag
           plCDFVal(ic "w") plCDFVal(ic "fw") plCDFVal(ic "l") plCDFVal(ic "m")
           plCDFVal(ic "fingers") plCDFVal(ic "model"))
    printf("PL-PROP %L w=%L fw=%L l=%L m=%L fingers=%L simW=%L model=%L\n" tag
           plProp(inst "w") plProp(inst "fw") plProp(inst "l") plProp(inst "m")
           plProp(inst "fingers") plProp(inst "simW") plProp(inst "model"))
    printf("PL-INST %L parameters=%L bbox=%L\n" tag errset(inst->parameters) errset(inst->bBox))
  )
)

procedure(plFindInst(cv name)
  let((found)
    found = nil
    foreach(obj dbGet(cv "instances")
      if(dbGet(obj "name") == name found = obj)
    )
    found
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  inst = plFindInst(cv "mn_c")
  plRead(inst "BEFORE")

  printf("PL-STEP1-SET-PROPERTIES\n")
  printf("PL-STEP1 %L\n" errset(list(
    dbDeletePropByName(inst "l")
    dbCreateProp(inst "l" "string" "200n")
    dbCreateProp(inst "w" "string" "2u")
    dbCreateProp(inst "fw" "string" "2u")
    dbCreateProp(inst "m" "string" "1")
    dbCreateProp(inst "fingers" "string" "1")
    dbDeletePropByName(inst "simW")
    dbCreateProp(inst "simW" "string" "2u")))
  )
  plRead(inst "AFTER-STEP1")

  printf("PL-STEP2-SAVE-AND-REOPEN\n")
  printf("PL-STEP2-SAVE %L\n" errset(dbSave(cv)))
  dbClose(cv)
  cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  when(cv2
    plRead(plFindInst(cv2 "mn_c") "AFTER-REOPEN")
    dbClose(cv2)
  ,
    printf("PL-REOPEN-FAILED\n")
  )
,
  printf("PL-OPEN-FAILED\n")
)
printf("PL-PARSE: 200n=%L 2u=%L ln=%L 1=%L\n" cdfParseFloatString("200n")
       cdfParseFloatString("2u") cdfParseFloatString("ln") cdfParseFloatString("1"))
printf("PL_DONE\n")
exit()
