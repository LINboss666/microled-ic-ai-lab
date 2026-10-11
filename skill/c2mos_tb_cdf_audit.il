; c2mos_tb_cdf_audit.il -- READ-ONLY audit of the OA testbench cell microled_cells/c2mos_dff_tb.
;
; Why this file exists: the golden deck writes SPECTRE parameter names (val0/val1/period/delay/
; width/rise/fall), but analogLib's own CDF dictionary -- read off
; /opt/IC617/tools/dfII/etc/cdslib/artist/analogLib/{vdc,vpulse,cap}/data.dm -- names those same
; quantities v1/v2/per/td/tr/tf/pw/srcType and maps them through propMapping. A readback that looks
; up the Spectre names therefore cannot tell you whether the values were imported. This audit dumps
; BOTH layers (raw OA property and CDF value) for every parameter the dictionary really defines.
;
; Discipline, all of it a measured trap on this build:
;   * mode "r", no dbSave, no dbCreateProp/dbDeletePropByName, no cdfSetParamValue and no
;     cdfUpdateInstParam (the latter deletes instance properties here); no CDF callback is invoked
;     (the analogLib dump shows formInitProc nil, so the getters used here cannot fire one).
;   * an undeclared foreach variable is GLOBAL in this SKILL and clobbers a nested loop -> let.
;   * "t" is the protected true symbol -> terminals iterate as tm.
;   * errset returns a LIST: guard with car(errset(x)); only %L is used, nil-safe.
;   * a single unguarded error aborts the whole load, so every optional call is wrapped. Two
;     shapes measured as NOT available here and therefore wrapped: dbClose() on a ddGetObj result
;     ("argument #1 should be a database object"), and dbOpenCellViewByType(..."symbol" "symbol")
;     for a symbol view (the working form passes the view type as nil).
;   * procedure(NAME(args) BODY) -- the lambda list is NOT closed before the body.
;
; Run: SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_tb AUD_DUT=c2mos_dff_1bit \
;      bash scripts/sch_virtuoso.sh skill/c2mos_tb_cdf_audit.il 420 TB_CDF_AUDIT_DONE
printf("TBCA-BEGIN\n")

LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELL_ENV = getShellEnvVar("SCH3_CELLS")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_tb")
DUT_ENV = getShellEnvVar("AUD_DUT")
DUT = if(DUT_ENV DUT_ENV "c2mos_dff_1bit")
NL_ENV = getShellEnvVar("AUD_NETLIST")
RUN_NL = if(NL_ENV NL_ENV "0")

; union of every parameter name analogLib defines on vdc / vpulse / cap, from the vendor CDF dump
; in this same audit run. Names a master does not define return nil, so this sweep is a lookup.
AUD_NAMES = list("dc" "vdc" "acm" "acp" "xfm" "pacm" "pacp" "srcType" "edgetype" "mag" "phase"
                 "tc1" "tc2" "tnom" "noisefile" "fundname" "FNpairs" "F1" "N1" "v1" "v2" "per"
                 "td" "tr" "tf" "pw" "val0" "val1" "period" "delay" "width" "rise" "fall"
                 "c" "C" "model" "w" "l" "m" "scale" "ic" "area" "perim" "trise" "polyCoef" "type")

procedure(audProps(obj)
  let((lst pp nm)
    ; three plausible shapes for enumerating properties; whichever answers is reported as measured
    printf("TBCA-PROPSHAPE dbGet_properties=%L attr_properties=%L attr_propList=%L\n"
           car(errset(dbGet(obj "properties"))) car(errset(obj->properties))
           car(errset(obj->propList)))
    lst = car(errset(obj->properties))
    unless(lst lst = car(errset(obj->propList)))
    when(lst
      printf("TBCA-PROPSTART count=%L\n" car(errset(errset(length(lst)))))
      foreach(pp lst
        printf("TBCA-PROP name=%L value=%L\n" car(errset(pp->name)) car(errset(pp->value))))
      )
    )
    ; the layer that AGENTS.md rule 27 says is the same storage as the CDF dictionary
    foreach(nm AUD_NAMES
      pp = car(errset(dbFindProp(obj nm)))
      when(pp
        printf("TBCA-RAWPROP name=%L value=%L\n" nm car(errset(dbGet(pp "value")))))
    )
  )
)

procedure(audCdf(ic)
  let((lst pp nm)
    lst = car(errset(ic->paramList))
    printf("TBCA-ENUM paramList=%L\n" if(lst errset(length(lst)) "nil"))
    when(lst
      foreach(pp lst
        printf("TBCA-CDF name=%L type=%L def=%L value=%L units=%L\n" car(errset(pp->name))
               car(errset(pp->type)) car(errset(pp->defaultValue)) car(errset(pp->value))
               car(errset(pp->units)))
      )
    )
    unless(lst
      foreach(nm AUD_NAMES
        pp = car(errset(cdfFindParamByName(ic nm)))
        when(pp
          printf("TBCA-CDF name=%L type=%L def=%L value=%L units=%L editable=%L\n"
                 car(errset(pp->name)) car(errset(pp->type)) car(errset(pp->defaultValue))
                 car(errset(pp->value)) car(errset(pp->units)) car(errset(pp->editable)))
        )
      )
    )
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
printf("TBCA-OPEN lib=%L cell=%L cv=%L\n" LIB CELL cv)
when(cv
  printf("TBCA-STRUCT instances=%L nets=%L terms=%L shapes=%L labels=%L\n"
         car(errset(errset(length(dbGet(cv "instances")))))
         car(errset(errset(length(dbGet(cv "nets")))))
         car(errset(errset(length(cv->terms))))
         car(errset(errset(length(dbGet(cv "shapes")))))
         car(errset(errset(length(cv->labels)))))
  audProps(cv)

  foreach(inst dbGet(cv "instances")
    master = car(errset(dbGet(inst "master")))
    its = car(errset(dbGet(inst "instTerms")))
    printf("TBCA-INST name=%L master=%L/%L/%L objType=%L instTerms=%L bbox=%L\n" inst->name
           if(master car(errset(dbGet(master "libName"))) "-")
           if(master car(errset(dbGet(master "cellName"))) "-")
           if(master car(errset(dbGet(master "viewName"))) "-")
           car(errset(dbGet(inst "objType")))
           if(its car(errset(errset(length(its)))) "nil")
           car(errset(inst->bBox)))
    audProps(inst)
    ic = car(errset(cdfGetInstCDF(inst)))
    printf("TBCA-CDFINST name=%L cdf=%L\n" inst->name if(ic "yes" "nil"))
    when(ic audCdf(ic))
    when(its
      foreach(it its
        printf("TBCA-CONNECT inst=%L term=%L net=%L direction=%L\n" inst->name car(errset(it->name))
               if(it->net car(errset(it->net->name)) "UNCONNECTED") car(errset(it->direction)))
      )
    )
  )

  foreach(net dbGet(cv "nets")
    printf("TBCA-NET name=%L instTerms=%L labels=%L shapes=%L isGlobal=%L\n" net->name
           car(errset(errset(length(net->instTerms))))
           car(errset(errset(length(net->labels))))
           car(errset(errset(length(net->shapes))))
           car(errset(dbGetProp(net "logicalConnection"))))
  )
  dbClose(cv)
)

; ---- DUT: schematic terminal objects vs symbol terminals (the terms=0 question) ----
dv = dbOpenCellViewByType(LIB DUT "schematic" "schematic" "r")
printf("TBCA-DUT-SCH cell=%L open=%L\n" DUT if(dv "yes" "nil"))
when(dv
  printf("TBCA-DUT-TERMS count=%L\n" car(errset(errset(length(dv->terms)))))
  dtm = car(errset(dv->terms))
  when(dtm
    foreach(tm dtm
      printf("TBCA-DUT-TERM name=%L dir=%L shape=%L\n" car(errset(tm->name))
             car(errset(tm->direction)) car(errset(tm->objType)))
    )
  )
  audProps(dv)
  dbClose(dv)
)
sv = dbOpenCellViewByType(LIB DUT "symbol" nil "r")
printf("TBCA-DUT-SYM cell=%L open=%L view=%L\n" DUT sv
       car(errset(if(sv dbGet(sv "viewName") "-"))))
when(sv
  sytm = car(errset(sv->terminals))
  printf("TBCA-DUT-SYMTERM count=%L\n" if(sytm car(errset(errset(length(sytm)))) "nil"))
  when(sytm
    foreach(tm sytm
      printf("TBCA-DUT-SYMTERM name=%L dir=%L\n" car(errset(tm->name)) car(errset(tm->direction))))
  )
  dbClose(sv)
)

; ---- what a netlister would need: implementation / simulation properties on the cellviews ----
procedure(audSim(lib cell view)
  let((dd nm)
    dd = car(errset(ddGetObj(lib cell view)))
    printf("TBCA-SIMOBJ lib=%L cell=%L view=%L dd=%L\n" lib cell view dd)
    when(dd
      foreach(nm list("simViewList" "simCompileList" "modelFile" "implementationPath" "source"
                      "analogCell" "simulatorLanguage")
        printf("TBCA-SIMPROP %L/%L/%L prop=%L value=%L\n" lib cell view nm
               car(errset(dbGetProp(dd nm))))
      )
      printf("TBCA-SIMVIEWS %L/%L/%L views=%L\n" lib cell view
             car(errset(errset(dbGetCellViewList(car(errset(ddGetObj(lib cell))))))))
      ; ddGetObj results are NOT db objects: dbClose on one aborts the load (measured), so no
      ; close is attempted here.
    )
  )
)
audSim(LIB CELL "schematic")
audSim(LIB DUT "schematic")
audSim("analogLib" "vdc" "symbol")
audSim("analogLib" "vpulse" "symbol")
audSim("analogLib" "cap" "symbol")

; ---- native netlisting: only when explicitly requested, and only ever into /tmp ----
printf("TBCA-NETLIST run=%L\n" RUN_NL)
when(RUN_NL == "1"
  ncv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  printf("TBCA-NL-CV %L\n" ncv)
  ; the tmpDir-anchored shape goes FIRST: if a session is created at all, it must not be allowed
  ; to write into the project working directory (cadence_work is CWD for this run).
  s0 = errset(asiCreateSession(?simulator "spectre" ?cellView ncv ?tmpDir "/tmp/tb_audit/nl"))
  printf("TBCA-NL-A0 %L\n" s0)
  s1 = errset(asiCreateSession(?simulator "spectre" ?cellView ncv))
  printf("TBCA-NL-A1 %L\n" s1)
  s2 = errset(asiCreateSession(?simulator "spectre" ?libName LIB ?cellName CELL
                               ?viewName "schematic"))
  printf("TBCA-NL-A2 %L\n" s2)
  sess = car(s0)
  unless(sess sess = car(s1))
  unless(sess sess = car(s2))
  printf("TBCA-NL-SESSION %L\n" sess)
  when(sess
    printf("TBCA-NL-INIT %L\n" errset(asiInitialize(sess)))
    printf("TBCA-NL-RUN %L\n" errset(asiNetlist(sess)))
    printf("TBCA-NL-FINAL %L\n" errset(asiFinalNetlist(sess)))
  )
  when(ncv dbClose(ncv))
)

printf("TB_CDF_AUDIT_DONE\n")
exit()
