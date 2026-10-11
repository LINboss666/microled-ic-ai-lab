; Migration helper for this session ONLY (not part of the repository).
; Approved F1/F2 second half: remove the stale `simW` property that spiceIn left on the imported
; data-driver devices. simW is NOT in the CDF dictionary of n33 / n33_dnw_4t_ckt, so it is inert to
; the CDF, but the operator's acceptance target is `simW ABSENT`.
;
; Scope discipline, and how this file PROVES it: every instance's model, master, l/w/fw/m/fingers
; values and its D/G/S/B net bindings are printed BEFORE and AFTER each delete, together with the
; cellview's instance/net/shape/term counts. Nothing but dbDeletePropByName(inst "simW") is called,
; then dbSave. No net, wire, figure, terminal, size or topology edit; no CDF callback, no
; cdfUpdateInstParam (measured in SCH-2 to delete instance properties), nothing against the PDK.
;
; Same open/save posture as the tested skill/sch3_fix_params.il: mode "a", dbSave, dbClose.
; Run: SCH3_LIB=microled_cells SCH3_CELLS="data_sink_1ch data_bias_ref" \
;      bash sch_virtuoso.sh skill/qoder_del_simw.il 600 DS_DONE
printf("DS-BEGIN\n")
LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELLS_ENV = getShellEnvVar("SCH3_CELLS")
CELLS_STR = if(CELLS_ENV CELLS_ENV "data_sink_1ch")
CELLS = car(errset(parseString(CELLS_STR " ")))
printf("DS-LIB %L CELLS %L\n" LIB CELLS)

procedure(dsProp(inst nm)
  let((pp)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp car(errset(dbGet(pp "value"))) "ABSENT")
  )
)

procedure(dsNet(inst pin)
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

procedure(dsSnap(cv tag)
  printf("%s-SUMMARY instances=%L nets=%L shapes=%L terms=%L\n" tag
         errset(length(dbGet(cv "instances"))) errset(length(dbGet(cv "nets")))
         errset(length(dbGet(cv "shapes"))) errset(length(cv->terms)))
  foreach(inst dbGet(cv "instances")
    printf("%s-INST %L model=%L master=%L/%L l=%L w=%L fw=%L m=%L fingers=%L simW=%L D=%L G=%L S=%L B=%L\n"
      tag inst->name inst->model
      car(errset(dbGet(dbGet(inst "master") "libName")))
      car(errset(dbGet(dbGet(inst "master") "cellName")))
      dsProp(inst "l") dsProp(inst "w") dsProp(inst "fw") dsProp(inst "m")
      dsProp(inst "fingers") dsProp(inst "simW")
      dsNet(inst "D") dsNet(inst "G") dsNet(inst "S") dsNet(inst "B"))
  )
)

foreach(CELL CELLS
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
  if(cv
    printf("DS-OPENED %L/%L\n" LIB CELL)
  ,
    printf("DS-OPEN-FAILED %L\n" CELL)
  )
  when(cv
    dsSnap(cv "DS-BEFORE")
    foreach(inst dbGet(cv "instances")
      when(dsProp(inst "simW") != "ABSENT"
        printf("DS-DEL %L simW_was=%L del=%L\n" inst->name dsProp(inst "simW")
               errset(dbDeletePropByName(inst "simW")))
        printf("DS-DEL-VERIFY %L simW_now=%L\n" inst->name dsProp(inst "simW"))
      )
    )
    dsSnap(cv "DS-AFTER")
    printf("DS-SAVE %L\n" errset(dbSave(cv)))
    dbClose(cv)
    printf("DS-CLOSED %L\n" CELL)
  )
)
printf("DS_DONE\n")
exit()
