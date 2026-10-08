; SCH-2 Part C, probe 3: read CDF parameter objects with the arrow accessor.
;
; probe 2 proved three things: the vendor views open when viewType is passed as nil; the n18 CDF
; really defines l, w, fw, m, fingers and model (and NOT wf/mult/area/nws); and every attribute read
; through dbGet() on a cdf: object came back nil, which means dbGet is the wrong accessor for CDF
; objects, not that the parameters are empty. This probe therefore uses obj->attribute so the
; parameter dictionary is quoted from the PDK itself instead of from anyone's memory. Read-only.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch2_cdf_probe3.il 600 CF_DONE
printf("CF-BEGIN\n")
procedure(cfOne(cdfObj where pn)
  let((pp)
    pp = car(errset(cdfFindParamByName(cdfObj pn)))
    printf("CF-P %L %L found=%L name=%L type=%L units=%L default=%L value=%L form=%L prompt=%L\n"
           where pn if(pp "yes" "no") pp->name pp->type pp->units pp->defaultValue pp->value
           pp->form pp->prompt)
  )
)
ddCell = car(errset(ddGetObj("smic18mmrf" "n18")))
sym = car(errset(dbOpenCellViewByType("smic18mmrf" "n18" "symbol" nil "r")))
base = car(errset(cdfGetBaseCellCDF(ddCell)))
eff = car(errset(cdfGetCellCDF(ddCell)))
printf("CF-OBJECTS sym=%L base=%L eff=%L\n" sym base eff)
foreach(pn list("l" "w" "fw" "m" "fingers" "model") cfOne(base "BASE" pn) )
foreach(pn list("l" "w" "fw" "m" "fingers" "model") cfOne(eff "EFFECTIVE" pn) )
printf("CF-VIEW-PARAMS %L\n" errset(sym->parameters))
printf("CF-VIEW-CELL %L objType=%L viewName=%L\n" errset(sym->cell) errset(sym->objType) errset(sym->viewName))
cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv
  inst = car(dbGet(cv "instances"))
  ic = car(errset(cdfGetInstCDF(inst)))
  printf("CF-INST objType=%L name=%L cdf=%L params=%L\n" errset(inst->objType) errset(inst->name) ic errset(inst->parameters))
  foreach(pn list("l" "w" "fw" "m" "fingers" "model") cfOne(ic "INSTANCE-CDF" pn) )
  dbClose(cv)
)
printf("CF_DONE\n")
exit()
