; SCAN-1 S3-C section 0: read-only capability and structure probe for the eight-cell build.
;
; Why this file exists: S3-C must deliver schematic AND symbol views of a circuit that is already
; measured, using only OA APIs that have been proven on THIS build. Three things are still unknown
; and each one decides part of the build, so they are measured instead of assumed:
;   A  the four masters the golden masters name (n18 p18 n33 p33) -- their OA cell views, their
;      symbol terminal NAMES AND ORDER (section 3 forbids reading terminal order off the picture or
;      off a port ordinal), and their CDF parameter dictionary with defaults;
;   B  what a spiceIn/ASG-generated symbol actually contains on this build (SCH-1/SCH-3 proved the
;      schematic side; S3-C needs the symbol side and needs to know whether the netlist's
;      `parameters <name> input|output|inputOutput` declarations become symbol terminal directions);
;   C  whether a schematic's port objects are readable at all in a batch session, or only through
;      the iopin instances (SCH-3 measured cv->terms empty and recorded that as a build limit).
;
; Strictly read-only: every dbOpenCellViewByType uses mode "r", there is no dbSave, no dbCreateProp,
; no dbDeletePropByName, no CDF callback. Nothing in the PDK, in microled_cells or in any existing
; library is written by this file.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c_oa_probe.il 600 S3CP_DONE
printf("S3CP-BEGIN\n")

s3cpNames = list("l" "w" "fw" "wf" "m" "mult" "nf" "fingers" "area" "as" "ad" "ps" "pd"
                 "model" "bulk" "simW" "simL" "length" "width" "multiplier")

procedure(s3cpParam(cdfObj where cellName pn)
  let((pp)
    pp = car(errset(cdfFindParamByName(cdfObj pn)))
    printf("S3CP-P %L %L %L found=%L type=%L units=%L default=%L value=%L form=%L\n"
           where cellName pn if(pp "yes" "no")
           if(pp pp->type "-") if(pp pp->units "-")
           if(pp pp->defaultValue "-") if(pp pp->value "-") if(pp pp->form "-"))
  )
)

procedure(s3cpMaster(cellName)
  let((ddc sym base eff views lst termIdx termIdxN)
    ddc = car(errset(ddGetObj("smic18mmrf" cellName)))
    sym = car(errset(dbOpenCellViewByType("smic18mmrf" cellName "symbol" nil "r")))
    base = car(errset(cdfGetBaseCellCDF(ddc)))
    eff = car(errset(cdfGetCellCDF(ddc)))
    printf("S3CP-M %L dd=%L symbolView=%L baseCDF=%L effCDF=%L\n"
           cellName if(ddc "yes" "NO") if(sym "yes" "NO") if(base "yes" "NO")
           if(eff "yes" "NO"))
    views = car(errset(dbGetCellViewList(ddc)))
    printf("S3CP-VIEWS %L %L\n" cellName views)
    when(sym
      lst = sym->terminals
      printf("S3CP-SYMTTERM %L count=%L\n" cellName length(lst))
      termIdx = 0
      foreach(termIdxN lst
        termIdx = termIdx + 1
        printf("S3CP-TERM %L ordinal=%L name=%L dir=%L\n" cellName termIdx
               termIdxN->name termIdxN->direction)
      )
      dbClose(sym)
    )
    foreach(pn s3cpNames s3cpParam(base "BASE" cellName pn))
    foreach(pn list("l" "w" "fw" "m" "fingers" "model" "simW")
      s3cpParam(eff "EFF" cellName pn))
  )
)

foreach(cellName list("n18" "p18" "n33" "p33") s3cpMaster(cellName))

printf("S3CP-API dbOpenCellViewByType=%L dbSave=%L dbCheck=%L dbCreateInst=%L dbCreateTerm=%L dbCreatePin=%L dbCreateFig=%L dbCreateCellView=%L ddCreateCell=%L dbCreateProp=%L dbDeletePropByName=%L dbFindProp=%L cdfGetInstCDF=%L cdfParseFloatString=%L\n"
       getd('dbOpenCellViewByType) getd('dbSave) getd('dbCheck) getd('dbCreateInst)
       getd('dbCreateTerm) getd('dbCreatePin) getd('dbCreateFig) getd('dbCreateCellView)
       getd('ddCreateCell) getd('dbCreateProp) getd('dbDeletePropByName) getd('dbFindProp)
       getd('cdfGetInstCDF) getd('cdfParseFloatString))
printf("S3CP-API-EDITOR schCheck=%L schCreate=%L schCreateWire=%L schCreateSym=%L symCreate=%L schConvSch2Sym=%L hiCreateDirLib=%L hiCheckAndSave=%L dbCopyCellView=%L\n"
       getd('schCheck) getd('schCreate) getd('schCreateWire) getd('schCreateSym)
       getd('symCreate) getd('schConvSch2Sym) getd('hiCreateDirLib) getd('hiCheckAndSave)
       getd('dbCopyCellView))

; ---- B/C: one already-delivered ASG cell, read-only, to learn the symbol + port structure
procedure(s3cpPinNets(obj)
  let((r)
    r = nil
    foreach(x obj->instTerms
      r = cons(if(x->net x->net->name "UNBOUND") r))
    r
  )
)

procedure(s3cpAsgCell(cellName)
  let((cv sym mosCount termObj fig figTypes netObj)
    cv = car(errset(dbOpenCellViewByType("microled_cells" cellName "schematic" "schematic" "r")))
    printf("S3CP-ASG %L schematic=%L\n" cellName if(cv "yes" "NO"))
    when(cv
      printf("S3CP-ASG-SUM %L instances=%L nets=%L terms=%L shapes=%L\n" cellName
             length(dbGet(cv "instances")) length(dbGet(cv "nets")) length(cv->terms)
             length(dbGet(cv "shapes")))
      foreach(obj dbGet(cv "terms")
        printf("S3CP-ASG-TERM %L name=%L dir=%L net=%L\n" cellName obj->name obj->direction
               if(obj->net obj->net->name "-"))
      )
      mosCount = 0
      foreach(obj dbGet(cv "instances")
        when(dbGet(obj "model") mosCount = mosCount + 1)
        unless(dbGet(obj "model")
          printf("S3CP-ASG-PORTINST %L name=%L master=%L/%L:%L terms=%L nets=%L\n" cellName
                 obj->name dbGet(dbGet(obj "master") "libName")
                 dbGet(dbGet(obj "master") "cellName") dbGet(dbGet(obj "master") "viewName")
                 car(errset(length(obj->instTerms)))
                 s3cpPinNets(obj))
        )
      )
      printf("S3CP-ASG-MOSCOUNT %L %L\n" cellName mosCount)
      foreach(netObj dbGet(cv "nets")
        printf("S3CP-ASG-NET %L name=%L pins=%L instTerms=%L termViews=%L\n" cellName
               netObj->name car(errset(length(netObj->pins)))
               car(errset(length(netObj->instTerms)))
               car(errset(length(netObj->termViews))))
      )
      dbClose(cv)
    )
    sym = car(errset(dbOpenCellViewByType("microled_cells" cellName "symbol" nil "r")))
    printf("S3CP-ASGSYM %L symbol=%L\n" cellName if(sym "yes" "NO"))
    when(sym
      printf("S3CP-ASGSYM-SUM %L figures=%L terms=%L terminals=%L\n" cellName
             car(errset(length(dbGet(sym "figures")))) car(errset(length(sym->terms)))
             length(sym->terminals))
      foreach(termIdxN sym->terminals
        printf("S3CP-ASGSYM-TERM %L name=%L dir=%L\n" cellName termIdxN->name
               termIdxN->direction))
      figTypes = nil
      foreach(fig dbGet(sym "figures")
        printf("S3CP-ASGSYM-FIG %L objType=%L objName=%L\n" cellName fig->objType
               car(errset(fig->objName))))
      dbClose(sym)
    )
  )
)

foreach(cellName list("c2mos_dff_1bit" "data_sink_1ch") s3cpAsgCell(cellName))

; does the file-scope wrapper cell of SCH-1/SCH-3 have a symbol? decides whether S3-C needs a
; topCell that is a subckt (and therefore an importer shell) or can be the file scope itself.
printf("S3CP-SHELL-SYMBOL sch3_top=%L sch1_import_top=%L\n"
       car(errset(dbOpenCellViewByType("microled_cells" "sch3_top" "symbol" nil "r")))
       car(errset(dbOpenCellViewByType("microled_cells" "sch1_import_top" "symbol" nil "r"))))

printf("S3CP_DONE\n")
exit()
