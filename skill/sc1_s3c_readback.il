; SCAN-1 S3-C section 4: independent, read-only OpenAccess readback of the eight delivered cells.
;
; This runs in its own Virtuoso process, after the writing session has exited, so every row below
; comes off the disk rather than out of a still-open in-memory object. The comparison against the
; golden table happens afterwards in scripts/sc1_s3c_verify_oa.py, so a bug in the writer cannot
; hide a bug in the reader or the other way round.
;
; What is printed and why:
;   * the RAW OA property and the CDF dictionary value and the number cdfParseFloatString makes from
;     it, for l/w/fw/m/fingers plus simW. SCH-2 measured that the raw property and the CDF value can
;     disagree, so all three are shipped; simW is reported, never written (it is the PDK's own
;     iPar("w") field).
;   * every master terminal BY NAME, and the net attached to each of them, again by name. The
;     measured reason: the PDK's own symbol terminals are not in one order across families -- this
;     build reports n18/p18 as S,G,B,D and n33 as D,G,B,S and p33 as B,D,G,S -- so a fixed column
;     list keyed on position would mis-wire the body ties.
;   * sub-circuit instances separately, because a hierarchical cell carries no devices of its own and
;     its whole acceptance is which master each instance points at and how its pins bind.
;   * dbCheck, and the honest state of schCheck. schCheck belongs to the Schematic Editor package,
;     which scripts/sc1_s3c_oa_probe.il measured as undefined in this batch build (as are schCreate,
;     schCreateWire, schCreateSym, symCreate and schConvSch2Sym). dbCheck checks the OA object graph
;     and is reported as dbCheck -- never dressed up as the editor's Check-And-Save.
;
; Run: S3C_OUT=/root/microled_ai_project/cadence_work/s3c_oa/readback/oa_readback.log \
;      bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c_readback.il 900 S3CR_DONE
printf("S3CR-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
CELLS_ENV = car(errset(getShellEnvVar("S3C_CELLS")))
CELLS_STR = if(CELLS_ENV CELLS_ENV
               "c2mos_dff sc1_scan_gate sc1_ls_core_r2d sc1_ls_c1_r2d sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_s3b_p33_bank_7 sc1_scan_power_1ch_s3c")
CELLS = car(errset(parseString(CELLS_STR " ")))
; a device is an instance whose master lives in the foundry library. Instance->model is NOT the
; test: an instance of a design cell also carries a model property (its child cell name), which is
; how seven hierarchical rows got counted as devices in the first pass.
PDKLIB = "smic18mmrf"
printf("S3CR-LIB %L CELLS %L\n" LIB CELLS)
printf("S3CR-API dbCheck=%L schCheck=%L dbCreateFig=%L ddCreateCell=%L schCreateSym=%L symCreate=%L\n"
       getd('dbCheck) getd('schCheck) getd('dbCreateFig) getd('ddCreateCell)
       getd('schCreateSym) getd('symCreate))

procedure(s3crRaw(inst nm)
  let((pp)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp car(errset(dbGet(pp "value"))) "ABSENT")
  )
)

procedure(s3crCdf(inst nm)
  let((ic pp)
    ic = car(errset(cdfGetInstCDF(inst)))
    pp = car(errset(cdfFindParamByName(ic nm)))
    if(pp car(errset(pp->value)) "NO-CDF-PARAM")
  )
)

procedure(s3crNet(inst pin)
  let((res)
    res = "NO-SUCH-TERMINAL"
    foreach(obj dbGet(inst "instTerms")
      when(obj->name == pin
        res = if(obj->net obj->net->name "UNCONNECTED")))
    res
  )
)

procedure(s3crTermNames(inst)
  let((out)
    out = nil
    foreach(obj dbGet(inst "instTerms") out = cons(obj->name out))
    car(errset(sort(out 'alphalessp)))
  )
)

procedure(s3crInstNets(inst)
  let((out)
    out = nil
    foreach(obj dbGet(inst "instTerms")
      out = cons(list(obj->name if(obj->net obj->net->name "UNBOUND")) out))
    out
  )
)

foreach(CELL CELLS
  cv = car(errset(dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")))
  when(cv
    printf("S3CR-CELL cell=%L instances=%L nets=%L shapes=%L terms=%L\n" CELL
           length(dbGet(cv "instances")) length(dbGet(cv "nets")) length(dbGet(cv "shapes"))
           length(cv->terms))
    printf("S3CR-DBCHECK cell=%L result=%L\n" CELL car(errset(dbCheck(cv))))
    foreach(obj dbGet(cv "instances")
      ; classification is by the master's library, not by the presence of a model property: an
      ; instance of a design cell carries model=<child cell name> on this build (measured in the
      ; ASG log), so a model test alone would print the seven sub-circuit instances as devices.
      if(dbGet(dbGet(obj "master") "libName") == PDKLIB
        printf("S3CR-MOS cell=%L inst=%L master=%L/%L:%L model=%L raw_l=%L raw_w=%L raw_fw=%L raw_m=%L raw_fingers=%L raw_simW=%L cdf_l=%L cdf_w=%L cdf_fw=%L cdf_m=%L cdf_fingers=%L cdf_model=%L num_l=%L num_w=%L terminals=%L D=%L G=%L S=%L B=%L bbox=%L\n"
               CELL obj->name dbGet(dbGet(obj "master") "libName")
               dbGet(dbGet(obj "master") "cellName") dbGet(dbGet(obj "master") "viewName")
               obj->model
               s3crRaw(obj "l") s3crRaw(obj "w") s3crRaw(obj "fw") s3crRaw(obj "m")
               s3crRaw(obj "fingers") s3crRaw(obj "simW")
               s3crCdf(obj "l") s3crCdf(obj "w") s3crCdf(obj "fw") s3crCdf(obj "m")
               s3crCdf(obj "fingers") s3crCdf(obj "model")
               car(errset(cdfParseFloatString(s3crCdf(obj "l"))))
               car(errset(cdfParseFloatString(s3crCdf(obj "w"))))
               s3crTermNames(obj)
               s3crNet(obj "D") s3crNet(obj "G") s3crNet(obj "S") s3crNet(obj "B")
               car(errset(obj->bBox)))
        printf("S3CR-INST cell=%L inst=%L master=%L/%L:%L model=%L instTerms=%L bindings=%L\n"
               CELL obj->name dbGet(dbGet(obj "master") "libName")
               dbGet(dbGet(obj "master") "cellName") dbGet(dbGet(obj "master") "viewName")
               car(errset(obj->model)) car(errset(length(obj->instTerms)))
               s3crInstNets(obj)))
    )
    foreach(obj cv->terms
      printf("S3CR-TERM cell=%L name=%L dir=%L net=%L\n" CELL obj->name obj->direction
             if(obj->net obj->net->name "-"))
    )
    foreach(netObj dbGet(cv "nets")
      printf("S3CR-NET cell=%L name=%L pins=%L instTerms=%L termViews=%L\n" CELL netObj->name
             car(errset(length(netObj->pins))) car(errset(length(netObj->instTerms)))
             car(errset(length(netObj->termViews))))
      ; a port net is a net that owns a pin. The pin object itself is printed because "the port is
      ; really bound" must be read off the pin, not inferred from a name that happens to match.
      foreach(pObj car(errset(netObj->pins))
        printf("S3CR-PIN cell=%L net=%L dir=%L term=%L objType=%L ownerInst=%L figTerm=%L\n" CELL
               netObj->name car(errset(pObj->direction)) car(errset(pObj->term))
               car(errset(pObj->objType))
               car(errset(if(pObj->obj pObj->obj->name "-")))
               car(errset(if(pObj->fig pObj->fig->name "-"))))
      )
    )
    dbClose(cv)
  )
  unless(cv printf("S3CR-OPEN-FAILED %L\n" CELL))

  sym = car(errset(dbOpenCellViewByType(LIB CELL "symbol" nil "r")))
  when(sym
    printf("S3CR-SYM cell=%L figures=%L terms=%L terminals=%L\n" CELL
           car(errset(length(dbGet(sym "figures")))) car(errset(length(sym->terms)))
           length(sym->terminals))
    foreach(termIdx sym->terminals
      printf("S3CR-SYMT cell=%L name=%L dir=%L\n" CELL termIdx->name termIdx->direction))
    dbClose(sym)
  )
  unless(sym printf("S3CR-SYM-MISSING %L\n" CELL))
)
printf("S3CR_DONE\n")
exit()
