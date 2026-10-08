; SCH-3 section 9/10: write the golden sizes onto a data-driver cellview through the parameter
; names that cell's own CDF defines.
;
; Where this differs from SCH-2, and why:
;   * no simW property. simW is not in the CDF dictionary of n33 or n33_dnw_4t_ckt (measured in
;     skill/sch3_cdf_probe.il: the masters define l/w/fw/m/fingers/model plus as/ad/ps/pd), SCH-3
;     section 7 forbids writing a property that does not exist and treating the width as set, and
;     the width lands correctly in w/fw anyway.
;   * the sizes come from a table generated out of the accepted golden deck by
;     scripts/sch2_gen_param_skill.py, one table per cellview, with the expected row count passed
;     in, so a table that does not match the cell stops the run instead of half-fixing it.
;
; Deliberately NOT done: cdfUpdateInstParam (measured to delete instance properties rather than
; commit them), dbCheck while parameters change (connectivity is already bound), any wire or figure
; edit, any write against the PDK. Instance set, names, masters, nets and pins are untouched.
;
; Run: SCH3_CELL=data_pdk_param_smoke SCH3_TABLE=/root/microled_ai_project/skill/sch3_smoke_table.gen.il \
;      bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch3_fix_params.il 600 FX3_DONE
printf("FX3-BEGIN\n")
TABLE = getShellEnvVar("SCH3_TABLE")
when(TABLE load(car(errset(getShellEnvVar("SCH3_TABLE")))))
LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH3_CELL")
CELL = if(CELL_ENV CELL_ENV "data_pdk_param_smoke")
PDKLIB = "smic18mmrf"

; honest capability evidence for section 12: the editor API is probed, not assumed
printf("FX3-API schCheck=%L dbSave=%L dbCheck=%L schCreate=%L\n"
       getd('schCheck) getd('dbSave) getd('dbCheck) getd('schCreate))

procedure(fx3Find(cv name)
  let((found)
    found = nil
    foreach(obj dbGet(cv "instances")
      if(dbGet(obj "name") == name found = obj)
    )
    found
  )
)

procedure(fx3Prop(inst nm value)
  let((made)
    errset(dbDeletePropByName(inst nm))
    made = errset(dbCreateProp(inst nm "string" value))
    printf("FX3-PROP %L %L => %L\n" inst->name nm car(made))
  )
)

procedure(fx3ReadCDF(inst tag)
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
    printf("FX3-CDF %L %L l=%L w=%L fw=%L m=%L fingers=%L\n" tag inst->name vl vw vfw vm vf)
  )
)

when(getShellEnvVar("SCH3_TABLE") == nil
  printf("FX3-NO-TABLE\n")
)
unless(getShellEnvVar("SCH3_TABLE") == nil
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
  when(cv
    ; the guard is against the cellview, not against a number typed into the environment: a table
    ; that is short by one device would otherwise fix the devices it knows and leave the rest on
    ; the PDK default, which is the exact failure mode this whole round exists to catch
    mosFound = 0
    foreach(inst dbGet(cv "instances")
      when(dbGet(dbGet(inst "master") "libName") == PDKLIB mosFound = mosFound + 1)
    )
    printf("FX3-OPENED %L/%L instances=%L pdkMos=%L tableRows=%L\n" LIB CELL
           length(dbGet(cv "instances")) mosFound length(sch1ParamTable))
    when(mosFound != length(sch1ParamTable)
      printf("FX3-ROWCOUNT-MISMATCH refusing to write\n")
    )
    unless(mosFound != length(sch1ParamTable)
      foreach(row sch1ParamTable
        inst = fx3Find(cv car(row))
        unless(inst printf("FX3-MISSING-INSTANCE %L\n" car(row)))
        when(inst
          printf("FX3-BEFORE %L model=%L master=%L/%L\n" inst->name dbGet(inst "model")
                 dbGet(dbGet(inst "master") "libName") dbGet(dbGet(inst "master") "cellName"))
          fx3Prop(inst "l" nth(2 row))
          fx3Prop(inst "w" nth(3 row))
          fx3Prop(inst "fw" nth(4 row))
          fx3Prop(inst "m" "1")
          fx3Prop(inst "fingers" "1")
          fx3ReadCDF(inst "AFTER-IN-MEMORY")
        )
      )
      printf("FX3-SAVE %L\n" errset(dbSave(cv)))
    )
    dbClose(cv)
  )
  unless(cv printf("FX3-OPEN-FAILED %L\n" CELL))
)
printf("FX3_DONE\n")
exit()
