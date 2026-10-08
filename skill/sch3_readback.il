; SCH-3 section 10: independent, read-only OA readback of the data-driver cellviews.
;
; Same discipline as SCH-2: this file does not know the golden table and prints nothing it has not
; been told by the database. For every instance it reports the raw OA property, the CDF dictionary
; value, the number cdfParseFloatString makes from that value, the bbox and the net attached to each
; master terminal BY NAME (the SCH-3 section 5 risk is exactly a terminal mapped by position). It
; also reports, per master, what the PDK's own CDF default is -- the integrity gate refuses to run
; if the defaults it was handed differ from these, because reusing n18's 180n/220n for a 3.3 V
; master would switch the default-fall-back detector off (measured: n33 defaults are 350n/350n).
;
; Comparison against the golden happens afterwards in scripts/sch_parameter_integrity_check.py, so a
; bug in the writer cannot hide a bug in the reader or the other way round.
;
; Run: SCH3_CELLS="data_sink_1ch data_bias_ref" \
;      bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch3_readback.il 600 RD3_DONE
printf("RD3-BEGIN\n")
LIB = "microled_cells"
CELLS_ENV = getShellEnvVar("SCH3_CELLS")
CELLS_STR = if(CELLS_ENV CELLS_ENV "data_pdk_param_smoke")
CELLS = car(errset(parseString(CELLS_STR " ")))
printf("RD3-CELLS %L\n" CELLS)

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

; every terminal the instance really has, by name, so a renamed or extra terminal is visible
; instead of being silently dropped by a fixed D/G/S/B column list
procedure(rdTermNames(inst)
  let((out)
    out = nil
    foreach(obj dbGet(inst "instTerms") out = cons(obj->name out))
    car(errset(sort(out 'alphalessp)))
  )
)

; what the master's own CDF says a parameter is by default, read off the vendor cell, read-only
procedure(rdMasterDefaults(inst)
  let((mc cdf nm pp)
    mc = dbGet(inst "master")
    when(mc
      cdf = car(errset(cdfGetCellCDF(dbGet(mc "cell"))))
      foreach(nm list("l" "w" "fw" "m" "fingers" "model")
        pp = car(errset(cdfFindParamByName(cdf nm)))
        printf("RD3-MPARAM cell=%L name=%L value=%L\n" dbGet(mc "cellName") nm
               if(pp car(errset(pp->value)) "UNREADABLE"))
      )
    )
  )
)

foreach(CELL CELLS
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  when(cv
    printf("RD-CELL %L/%L instances=%L nets=%L shapes=%L terms=%L\n" LIB CELL
           length(dbGet(cv "instances")) length(dbGet(cv "nets")) length(dbGet(cv "shapes"))
           length(cv->terms))
    foreach(inst dbGet(cv "instances")
      rdMasterDefaults(inst)
      when(inst->model
        printf("RD-ROW cell=%L inst=%L master_lib=%L master_cell=%L master_view=%L model=%L raw_l=%L raw_w=%L raw_fw=%L raw_fingers=%L raw_mult=%L simW=%L cdf_l=%L cdf_w=%L cdf_fw=%L cdf_fingers=%L cdf_mult=%L num_l=%L num_w=%L bbox=%L D=%L G=%L S=%L B=%L terms=%L\n"
          CELL inst->name dbGet(dbGet(inst "master") "libName")
          dbGet(dbGet(inst "master") "cellName")
          dbGet(dbGet(inst "master") "viewName") inst->model
          rdProp(inst "l") rdProp(inst "w") rdProp(inst "fw") rdProp(inst "fingers") rdProp(inst "m")
          rdProp(inst "simW")
          rdCDF(inst "l") rdCDF(inst "w") rdCDF(inst "fw") rdCDF(inst "fingers") rdCDF(inst "m")
          errset(cdfParseFloatString(rdCDF(inst "l"))) errset(cdfParseFloatString(rdCDF(inst "w")))
          errset(inst->bBox) rdNet(inst "D") rdNet(inst "G") rdNet(inst "S") rdNet(inst "B")
          rdTermNames(inst))
      )
    )
    foreach(term cv->terms
      printf("RD-PIN name=%L dir=%L net=%L\n" term->name term->direction
             if(term->net term->net->name "NO-NET"))
    )
    foreach(n dbGet(cv "nets")
      printf("RD-NET net=%L pins=%L instTerms=%L\n" n->name length(n->pins)
             car(errset(length(n->instTerms))))
      when(n->pins
        printf("RD-NETPIN net=%L pins=%L\n" n->name length(n->pins))
      )
    )
    dbClose(cv)
  )
  unless(cv
    printf("RD3-OPEN-FAILED %L\n" CELL)
  )
)
printf("RD3_DONE\n")
exit()
