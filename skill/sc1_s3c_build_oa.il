; SCAN-1 S3-C section 3: write the golden sizes onto the eight imported cellviews through the
; parameter names each master's own CDF defines, then save.
;
; Why this step exists at all: SCH-2 measured that spiceIn/ASG brings connectivity in correctly but
; leaves the device sizes in a property the CDF does not see, so an imported schematic can look
; right and simulate wrong. The sizes here come from a table generated out of the six frozen
; masters by scripts/sc1_s3c_golden.py -- not typed into this file -- and the row count is checked
; against the cellview before anything is written, because a table that is short by one device
; would otherwise fix the devices it knows and leave the rest on the PDK default.
;
; Deliberately NOT done: cdfUpdateInstParam (measured to delete instance properties on this build),
; writing a simW property (simW is the PDK's own iPar("w") field and is left exactly as the master
; defines it), any wire or figure edit, any write against the PDK or against an existing library.
; Instance set, names, masters, nets and pins are untouched -- only the five CDF size parameters.
;
; Run: S3C_TABLE=/root/microled_ai_project/cadence_work/s3c_oa/asg_in/sc1_s3c_param_table.gen.il \
;      bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c_build_oa.il 900 S3CB_DONE
printf("S3CB-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
TABLE = car(errset(getShellEnvVar("S3C_TABLE")))
when(TABLE load(TABLE))
CELLS_ENV = car(errset(getShellEnvVar("S3C_CELLS")))
CELLS_STR = if(CELLS_ENV CELLS_ENV
               "c2mos_dff sc1_scan_gate sc1_ls_core_r2d sc1_ls_c1_r2d sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_s3b_p33_bank_7 sc1_scan_power_1ch_s3c")
CELLS = car(errset(parseString(CELLS_STR " ")))
PDKLIB = "smic18mmrf"
; reading an unbound SKILL variable is an error, so the table reference is errset-wrapped and the
; whole write pass is refused unless the table both arrived and loaded.
loaded = car(errset(s3cParamTable))
printf("S3CB-LIB %L TABLE %L LOADED %L CELLS %L\n" LIB TABLE loaded CELLS)
printf("S3CB-API dbSave=%L dbCreateProp=%L dbDeletePropByName=%L cdfGetInstCDF=%L schCreate=%L\n"
       getd('dbSave) getd('dbCreateProp) getd('dbDeletePropByName) getd('cdfGetInstCDF)
       getd('schCreate))
when(or(TABLE == nil loaded == nil)
  printf("S3CB-REFUSE no parameter table loaded -- nothing is written\n"))

procedure(s3cbFind(cv name)
  let((found)
    found = nil
    foreach(obj dbGet(cv "instances")
      if(dbGet(obj "name") == name found = obj))
    found
  )
)

procedure(s3cbRaw(inst nm)
  let((pp)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp car(errset(dbGet(pp "value"))) "ABSENT")
  )
)

procedure(s3cbCdf(inst nm)
  let((ic pp)
    ic = car(errset(cdfGetInstCDF(inst)))
    pp = car(errset(cdfFindParamByName(ic nm)))
    if(pp car(errset(pp->value)) "NO-CDF-PARAM")
  )
)

procedure(s3cbSet(inst nm value)
  let((made)
    errset(dbDeletePropByName(inst nm))
    made = errset(dbCreateProp(inst nm "string" value))
    printf("S3CB-PROP %L %L wanted=%L made=%L\n" inst->name nm value car(made))
  )
)

procedure(s3cbRowsFor(cellName)
  let((out)
    out = 0
    foreach(row s3cParamTable when(nth(0 row) == cellName out = out + 1))
    out
  )
)

procedure(s3cbApply(cv cellName)
  foreach(row s3cParamTable
    when(nth(0 row) == cellName
      inst = s3cbFind(cv nth(1 row))
      when(inst
        printf("S3CB-BEFORE %L %L model=%L master=%L/%L raw_l=%L raw_w=%L raw_fw=%L raw_simW=%L cdf_l=%L cdf_w=%L\n"
               cellName inst->name inst->model
               dbGet(dbGet(inst "master") "libName") dbGet(dbGet(inst "master") "cellName")
               s3cbRaw(inst "l") s3cbRaw(inst "w") s3cbRaw(inst "fw") s3cbRaw(inst "simW")
               s3cbCdf(inst "l") s3cbCdf(inst "w"))
        s3cbSet(inst "l" nth(2 row))
        s3cbSet(inst "w" nth(3 row))
        s3cbSet(inst "fw" nth(4 row))
        s3cbSet(inst "m" nth(5 row))
        s3cbSet(inst "fingers" nth(6 row))
        printf("S3CB-AFTER %L %L raw_l=%L raw_w=%L raw_fw=%L raw_m=%L raw_fingers=%L raw_simW=%L cdf_l=%L cdf_w=%L cdf_fw=%L num_l=%L num_w=%L\n"
               cellName inst->name s3cbRaw(inst "l") s3cbRaw(inst "w") s3cbRaw(inst "fw")
               s3cbRaw(inst "m") s3cbRaw(inst "fingers") s3cbRaw(inst "simW")
               s3cbCdf(inst "l") s3cbCdf(inst "w") s3cbCdf(inst "fw")
               car(errset(cdfParseFloatString(s3cbCdf(inst "l"))))
               car(errset(cdfParseFloatString(s3cbCdf(inst "w")))))
      )
      unless(inst printf("S3CB-MISSING-INSTANCE %L %L\n" cellName nth(1 row)))
    )
  )
)

foreach(CELL CELLS
  cv = car(errset(dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")))
  when(cv
    mosFound = 0
    foreach(obj dbGet(cv "instances")
      when(dbGet(dbGet(obj "master") "libName") == PDKLIB mosFound = mosFound + 1))
    want = s3cbRowsFor(CELL)
    printf("S3CB-OPEN %L instances=%L pdkMos=%L tableRows=%L\n" CELL
           length(dbGet(cv "instances")) mosFound want)
    when(mosFound != want
      printf("S3CB-ROWCOUNT-MISMATCH %L pdkMos=%L rows=%L refusing to write this cell\n"
             CELL mosFound want))
    unless(mosFound != want
      when(and(TABLE != nil loaded != nil) s3cbApply(cv CELL))
      printf("S3CB-SAVE %L %L\n" CELL errset(dbSave(cv)))
    )
    dbClose(cv)
  )
  unless(cv printf("S3CB-OPEN-FAILED %L\n" CELL))
)
printf("S3CB_DONE\n")
exit()
