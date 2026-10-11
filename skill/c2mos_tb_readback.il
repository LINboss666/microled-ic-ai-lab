; c2mos_tb_readback.il -- read back an OA testbench cell: instance set, masters, terminals, the
; net bound to every terminal, the OA properties and the CDF parameter values.
;
; Read-only. dbOpenCellViewByType with mode "r"; nothing is saved, and no CDF callback or
; evaluation call (cdfUpdateInstParam / dbEvalParamCell / dbCheckParamCell) is made against any
; master, because SCH-2 measured that those write into the vendor library.
;
; Discipline, all of it paid for in this session:
;   * %L only -- a nil into %s aborts the whole load
;   * car(errset(...)) -- errset returns a LIST, so errset(x) == nil is never true
;   * no `~`, no funcall
;   * EVERY loop variable is declared in the enclosing let. An earlier revision used a bare `n`
;     in the helpers and again in the nets loop; in SKILL an undeclared loop variable is global,
;     so the loops clobbered each other, the instance walk yielded a nil element, and the real
;     failure surfaced much later as "dbClose: Invalid cellView".
;
; Run: SCH3_LIB=microled_cells SCH3_CELLS=c2mos_dff_tb \
;      bash scripts/sch_virtuoso.sh skill/c2mos_tb_readback.il 400 TBRB_DONE
printf("TB-BEGIN\n")
LIB_ENV = getShellEnvVar("SCH3_LIB")
LIB = if(LIB_ENV LIB_ENV "microled_cells")
CELLS_ENV = getShellEnvVar("SCH3_CELLS")
CELLS = car(errset(parseString(if(CELLS_ENV CELLS_ENV "c2mos_dff_tb") " ")))
NAMES = list("dc" "val0" "val1" "period" "delay" "width" "rise" "fall" "c" "model")

procedure(tbPropValue(inst nm)
  let((pp)
    pp = car(errset(dbFindProp(inst nm)))
    if(pp car(errset(dbGet(pp "value"))) "-")
  )
)

procedure(tbPropPairs(inst)
  let((out n)
    out = nil
    foreach(n NAMES
      when(tbPropValue(inst n) != "-" out = cons(list(n tbPropValue(inst n)) out)))
    reverse(out)
  )
)

procedure(tbCdfPairs(inst)
  let((ic out pp n)
    ic = car(errset(cdfGetInstCDF(inst)))
    out = nil
    when(ic
      foreach(n NAMES
        pp = car(errset(cdfFindParamByName(ic n)))
        when(pp out = cons(list(n car(errset(pp->value))) out))))
    reverse(out)
  )
)

procedure(tbTermList(inst)
  car(errset(dbGet(inst "instTerms")))
)

foreach(CELL CELLS
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  if(cv
    printf("TB-CELL %L/%L instances=%L nets=%L terms=%L\n" LIB CELL
           errset(length(dbGet(cv "instances"))) errset(length(dbGet(cv "nets")))
           errset(length(dbGet(cv "terms"))))
  ,
    printf("TB-OPEN-FAILED %L\n" CELL)
  )
  when(cv
    foreach(inst dbGet(cv "instances")
      printf("TB-INST name=%L master=%L/%L:%L model=%L\n" inst->name
             car(errset(dbGet(dbGet(inst "master") "libName")))
             car(errset(dbGet(dbGet(inst "master") "cellName")))
             car(errset(dbGet(dbGet(inst "master") "viewName")))
             car(errset(inst->model)))
      printf("TB-PROP %L %L\n" inst->name errset(tbPropPairs(inst)))
      printf("TB-CDF  %L %L\n" inst->name errset(tbCdfPairs(inst)))
      foreach(it tbTermList(inst)
        printf("TB-TERM inst=%L term=%L net=%L\n" inst->name car(errset(it->name))
               if(it->net car(errset(it->net->name)) "UNCONNECTED"))
      )
    )
    foreach(netObj dbGet(cv "nets")
      printf("TB-NET name=%L instTerms=%L\n" netObj->name
             car(errset(length(netObj->instTerms))))
    )
    errset(dbClose(cv))
  )
)
printf("TBRB_DONE\n")
exit()
