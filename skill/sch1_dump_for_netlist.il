; SCH-1 Part D: dump the saved cellview as key/value rows on stdout.
;
; scripts/sch1_netlist_from_db.py turns these rows into a Spectre netlist and a connectivity CSV.
; Nothing here knows the DFF: the rows are whatever the database holds. Exporting to stdout rather
; than to a file is deliberate -- printf(port ...) is not accepted by this build's printf (measured:
; "argument #1 should be a string (type template = tg)"), and the log is kept as raw evidence
; anyway.
;
; Run: SCH1_CELL=<cell> bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_dump_for_netlist.il 400 DUMP_DONE
printf("NL-BEGIN\n")
LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(nlNetOfPin(inst termName)
  let((res)
    res = "NO-SUCH-PIN"
    foreach(obj dbGet(inst "instTerms")
      when(dbGet(obj "name") == termName
        res = if(dbGet(obj "net") dbGet(dbGet(obj "net") "name") "UNCONNECTED")
      )
    )
    res
  )
)

procedure(nlPropVal(obj pname)
  let((pp)
    pp = errset(dbFindProp(obj pname))
    if(car(pp) car(errset(dbGet(car(pp) "value"))) "MISSING")
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv
  printf("NL-CELL lib=%s cell=%s view=%s\n" LIB CELL dbGet(cv "viewName"))
  printf("NL-SUMMARY instances=%d nets=%d shapes=%d\n" length(dbGet(cv "instances"))
         length(dbGet(cv "nets")) length(dbGet(cv "shapes")))
  foreach(obj dbGet(cv "instances")
    mdl = dbGet(obj "model")
    mview = dbGet(dbGet(obj "master") "viewName")
    mlib = dbGet(dbGet(obj "master") "libName")
    mcell = dbGet(dbGet(obj "master") "cellName")
    when(mdl
      printf("NL-MOS inst=%s master=%s/%s:%s model=%s l_expr=%s w_expr=%s D=%s G=%s S=%s B=%s\n"
             dbGet(obj "name") mlib mcell mview mdl nlPropVal(obj "l") nlPropVal(obj "simW")
             nlNetOfPin(obj "D") nlNetOfPin(obj "G") nlNetOfPin(obj "S") nlNetOfPin(obj "B"))
    )
    unless(mdl
      ; port markers: the port identity is read from the net that owns the pin, not from here
      printf("NL-PINSTUB inst=%L master=%L/%L:%L
" dbGet(obj "name") mlib mcell mview)
    )
  )
  foreach(obj dbGet(cv "nets")
    pp = dbGet(obj "pins")
    when(pp
      printf("NL-PORT net=%L pinCount=%L firstPin=%L pinDir=%L termName=%L
" dbGet(obj "name")
             length(pp) car(pp) car(errset(dbGet(car(pp) "direction")))
             car(errset(dbGet(dbGet(car(pp) "term") "name"))))
    )
  )
  dbClose(cv)
,
  printf("NL-OPEN-FAILED\n")
)
printf("DUMP_DONE\n")
exit()
