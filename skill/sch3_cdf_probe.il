; SCH-3 Part D v4: read-only CDF audit for the 3.3 V masters the data driver uses.
;
; Accessor choice is itself a measured fact: dbGet(cdfObj "attr") returns nil for CDF objects on
; this build (probe v3 showed every t=/v=/u= nil while the parameter names resolved), so the
; dictionary is read with obj->attribute, the form SCH-2's probe3 proved. Same for terminals.
;
; What must not be assumed: the n18/p18 mapping (l/w/fw/m/fingers/model, 180n/220n/220n/1/1) found
; in SCH-2. The data driver uses n33 and the deep-N-well n33_dnw_4t_ckt, and the whole point of
; AGENTS.md rule 27 is that "same PDK, therefore same names/defaults" is unverified until measured.
;
; Read-only: no dbSave, no dbCreateProp, no CDF callback (cdfUpdateInstParam deletes instance
; properties on this build).
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch3_cdf_probe.il 600 S3CDF_DONE
printf("S3-BEGIN\n")

; wide candidate list: 1.2 V family, 3.3 V family, RF/multi-finger and DNW-flavoured names
s3Names = list("l" "w" "fw" "wf" "m" "mult" "n" "nf" "fingers" "area" "as" "ad" "ps" "pd" "nws"
               "model" "bulk" "b" "sub" "dnw" "wnw" "rmod" "length" "width" "multiplier"
               "temperature" "mtc" "dtc")

procedure(s3One(cdfObj where cell pn)
  let((pp)
    pp = car(errset(cdfFindParamByName(cdfObj pn)))
    printf("S3P %L %L %L found=%L type=%L units=%L default=%L value=%L form=%L prompt=%L\n"
           cell where pn if(pp "yes" "no") pp->type pp->units pp->defaultValue pp->value
           pp->form pp->prompt)
  )
)

procedure(s3ProbeMaster(lib cell)
  let((ddc sym base eff views lst term)
    ddc = car(errset(ddGetObj(lib cell)))
    sym = car(errset(dbOpenCellViewByType(lib cell "symbol" nil "r")))
    base = car(errset(cdfGetBaseCellCDF(ddc)))
    eff = car(errset(cdfGetCellCDF(ddc)))
    printf("S3-OBJ %L dd=%L sym=%L base=%L eff=%L\n" cell ddc sym base eff)
    views = car(errset(dbGetCellViewList(ddc)))
    printf("S3-VIEWS %L %L\n" cell views)
    when(sym
      lst = sym->terminals
      printf("S3-TERMCOUNT %L %L\n" cell length(lst))
      ; "t" is the protected true symbol in SKILL -- a loop variable called t is a measured trap
      foreach(term lst printf("S3-TERM %L %L dir=%L\n" cell term->name term->direction))
      dbClose(sym)
    )
    foreach(pn s3Names s3One(base "BASE" cell pn))
    foreach(pn list("l" "w" "fw" "m" "fingers" "model") s3One(eff "EFFECTIVE" cell pn))
  )
)

foreach(cell list("n33" "n33_dnw_4t_ckt" "n33_ckt" "n18")
  s3ProbeMaster("smic18mmrf" cell)
)

foreach(s list("2u" "2e-06" "20u" "5u" "350n" "180n" "220n" "0.35u" "ln")
  printf("S3-PARSE %L %L\n" s car(errset(cdfParseFloatString(s))))
)
printf("S3CDF_DONE\n")
exit()
