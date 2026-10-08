; SCH-2 Part E: write the golden sizes onto the schematic instances, through the parameter names the
; teacher PDK actually defines.
;
; The pilot proved three things and this script relies on all three: the CDF dictionary of these
; instances is fed by OA properties whose names must be exactly l, w, fw, m, fingers (a property
; named simW is invisible to the CDF, which is how every device ended up showing the default 220n);
; values must be numbers the CDF can parse, so "ln" is replaced by "200n"; and a property written
; this way survives dbSave plus a read-only reopen.
;
; Deliberately NOT done here: cdfUpdateInstParam / cdfUpdateInstSingleParam (measured to remove
; properties instead of committing them), dbCheck (connectivity is already bound and must not be
; recomputed while the parameters change), any wire or figure edit, and any write against the PDK.
; The instance set, names, masters, nets and pins are untouched -- only the parameter properties.
;
; Run: SCH1_CELL=c2mos_dff_1bit_paramfix bash scripts/sch_virtuoso.sh skill/sch2_fix_params.il 600 FX_DONE
printf("FX-BEGIN\n")
load("/root/microled_ai_project/skill/sch2_param_table.gen.il")
LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit_paramfix")

procedure(fxFind(cv name)
  let((found)
    found = nil
    foreach(obj dbGet(cv "instances")
      if(dbGet(obj "name") == name found = obj)
    )
    found
  )
)

procedure(fxProp(inst nm value)
  let((made)
    errset(dbDeletePropByName(inst nm))
    made = errset(dbCreateProp(inst nm "string" value))
    printf("FX-PROP %L %L => %L\n" inst->name nm car(made))
  )
)

procedure(fxReadCDF(inst tag)
  let((ic p vl vw vfw vm vf)
    ic = car(errset(cdfGetInstCDF(inst)))
    p = car(errset(cdfFindParamByName(ic "l")))
    vl = if(p car(errset(p->value)) "-")
    p = car(errset(cdfFindParamByName(ic "w")))
    vw = if(p car(errset(p->value)) "-")
    p = car(errset(cdfFindParamByName(ic "fw")))
    vfw = if(p car(errset(p->value)) "-")
    p = car(errset(cdfFindParamByName(ic "m")))
    vm = if(p car(errset(p->value)) "-")
    p = car(errset(cdfFindParamByName(ic "fingers")))
    vf = if(p car(errset(p->value)) "-")
    printf("FX-CDF %L %L l=%L w=%L fw=%L m=%L fingers=%L
" tag inst->name vl vw vfw vm vf)
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  printf("FX-OPENED %s/%s instances=%L\n" LIB CELL length(dbGet(cv "instances")))
  foreach(row sch1ParamTable
    inst = fxFind(cv car(row))
    unless(inst
      printf("FX-MISSING-INSTANCE %L\n" car(row))
    )
    when(inst
      printf("FX-BEFORE %L model=%L master=%L/%L\n" inst->name dbGet(inst "model")
             dbGet(dbGet(inst "master") "libName") dbGet(dbGet(inst "master") "cellName"))
      fxProp(inst "l" nth(2 row))
      fxProp(inst "w" nth(3 row))
      fxProp(inst "fw" nth(4 row))
      fxProp(inst "m" "1")
      fxProp(inst "fingers" "1")
      fxProp(inst "simW" nth(3 row))
      fxReadCDF(inst "AFTER")
    )
  )
  printf("FX-SAVE %L\n" errset(dbSave(cv)))
  dbClose(cv)
)
unless(cv
  printf("FX-OPEN-FAILED\n")
)
printf("FX_DONE\n")
exit()
