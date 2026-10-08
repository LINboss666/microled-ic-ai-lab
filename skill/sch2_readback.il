; SCH-2 Part F: independent readback of the schematic parameters, from a fresh session, read only.
;
; This file does not know the golden table and does not re-print it: for every instance it asks the
; database for the raw property values, the CDF dictionary values, the numbers cdfParseFloatString
; produces from those strings, the geometry bbox and the net attached to each master terminal. The
; comparison against the golden is done afterwards by scripts/sch_parameter_integrity_check.py, so
; a bug in the writer cannot hide a bug in the reader or the other way round.
;
; Run: SCH1_CELL=<cell> bash scripts/sch_virtuoso.sh skill/sch2_readback.il 600 RD_DONE
printf("RD-BEGIN\n")
LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit_paramfix")

procedure(rdProp(inst nm)
  let((pp)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp car(errset(dbGet(pp "value"))) "ABSENT")
  )
)

procedure(rdCDF(inst nm)
  let((ic pp)
    ic = car(errset(cdfGetInstCDF(inst)))
    pp = car(errset(cdfFindParamByName(ic nm)))
    if(pp car(errset(pp->value)) "NO-CDF-PARAM")
  )
)

procedure(rdNet(inst pin)
  let((res)
    res = "NO-PIN"
    foreach(obj dbGet(inst "instTerms")
      when(obj->name == pin
        res = if(obj->net obj->net->name "UNCONNECTED")
      )
    )
    res
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv
  printf("RD-CELL %L/%L instances=%L nets=%L shapes=%L\n" LIB CELL
         length(dbGet(cv "instances")) length(dbGet(cv "nets")) length(dbGet(cv "shapes")))
  foreach(inst dbGet(cv "instances")
    when(inst->model
      printf("RD-ROW inst=%L master_lib=%L master_cell=%L master_view=%L model=%L raw_l=%L raw_w=%L raw_fw=%L raw_fingers=%L raw_mult=%L simW=%L cdf_l=%L cdf_w=%L cdf_fw=%L cdf_fingers=%L cdf_mult=%L num_l=%L num_w=%L bbox=%L D=%L G=%L S=%L B=%L\n"
        inst->name dbGet(dbGet(inst "master") "libName") dbGet(dbGet(inst "master") "cellName")
        dbGet(dbGet(inst "master") "viewName") inst->model
        rdProp(inst "l") rdProp(inst "w") rdProp(inst "fw") rdProp(inst "fingers") rdProp(inst "m")
        rdProp(inst "simW")
        rdCDF(inst "l") rdCDF(inst "w") rdCDF(inst "fw") rdCDF(inst "fingers") rdCDF(inst "m")
        errset(cdfParseFloatString(rdCDF(inst "l"))) errset(cdfParseFloatString(rdCDF(inst "w")))
        errset(inst->bBox) rdNet(inst "D") rdNet(inst "G") rdNet(inst "S") rdNet(inst "B"))
    )
  )
  foreach(term cv->terms
    printf("RD-PIN %L\n" term->name)
  )
  foreach(n dbGet(cv "nets")
    when(n->pins
      printf("RD-NETPIN net=%L pins=%L\n" n->name length(n->pins))
    )
  )
  dbClose(cv)
)
unless(cv
  printf("RD-OPEN-FAILED\n")
)
printf("RD_DONE\n")
exit()
