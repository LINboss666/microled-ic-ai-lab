; SUPERSEDED: kept as the measured evidence that this build's printf() refuses a port as its
; first argument ("argument #1 should be a string (type template = tg)"). The working exporter is
; skill/sch1_dump_for_netlist.il + scripts/sch1_netlist_from_db.py.
; SCH-1 Part D: write a Spectre netlist and a connectivity CSV out of the SAVED cellview.
;
; Source of truth is the schematic database, never spectre/C2MOS_DFF.scs: every instance line is
; rebuilt from the instance name, the master's terminal names (D G S B) and the net each instance
; terminal is attached to, and model / l / w come from the instance properties. If the schematic
; disagrees with the golden netlist the difference shows up in the CSV and the checker stops the
; phase -- that is exactly why this exports instead of reusing the input file.
;
; Two side effects, both on our own cell, both announced by the lines they print:
;   * ASG's default 'masterCellForGnd' injected a basic/iopin instance (PIN0) on a new net named
;     gnd!. The accepted cell has no such object -- its ground is the vss port -- so PIN0 and the
;     now-empty gnd! net are removed here.
;   * dbCheck + dbSave run at the end, so what is on disk is what was exported.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_netlist_out.il 400 NL_DONE
printf("NL-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")
OUTDIR = "/root/microled_ai_project/cadence_out"
NLPATH = sprintf(nil "%s/%s_from_schematic.scs" OUTDIR CELL)
CSVPATH = sprintf(nil "%s/%s_connectivity.csv" OUTDIR CELL)

procedure(nlFindInst(theCv name)
  let((found)
    found = nil
    foreach(obj dbGet(theCv "instances")
      if(dbGet(obj "name") == name found = obj)
    )
    found
  )
)

procedure(nlPropVal(obj pname)
  let((pp)
    pp = errset(dbFindProp(obj pname))
    if(car(pp) errset(dbGet(car(pp) "value")) "MISSING")
  )
)

procedure(nlNetOfTerm(inst termName)
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

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  printf("NL-OPENED %s/%s\n" LIB CELL)
  pin0 = nlFindInst(cv "PIN0")
  printf("NL-HAVE-dbDeleteInst %L\n" getd('dbDeleteInst))
  when(pin0
    printf("NL-REMOVE-PIN0 %L\n" errset(dbDeleteInst(pin0)))
  )
  gnet = errset(dbFindNetByName(cv "gnd!"))
  when(car(gnet)
    printf("NL-REMOVE-GNDNET %L\n" errset(dbDeleteEmptyNet(car(gnet))))
  )

  ; ---- design variables: are their numeric values in the cellview at all?
  foreach(v list("ln" "wc" "wcp" "wk" "wkp")
    printf("NL-DESVAR %L prop=%L\n" v nlPropVal(cv v))
  )
  printf("NL-DESVAR-ATTR %L\n" errset(dbGet(cv "desVars")))

  ; ---- ports are whatever nets own a pin
  portNames = nil
  foreach(obj dbGet(cv "nets")
    when(dbGet(obj "pins")
      portNames = cons(dbGet(obj "name") portNames)
    )
  )
  portNames = reverse(portNames)
  printf("NL-PORT-FROM-DB %L\n" portNames)
  portString = errset(buildString(portNames " "))

  p1 = outfile(NLPATH "w")
  p2 = outfile(CSVPATH "w")
  when(p1
    printf(p1 "; SCH-1: netlist exported FROM microled_cells/%s:schematic by skill/sch1_netlist_out.il\n" CELL)
    printf(p1 "; port nets = the nets that own a pin in the cellview: %s\n" portString)
    printf(p1 "; instance lines are rebuilt from instance terminals and their attached nets\n")
    printf(p1 "simulator lang=spectre insensitive=yes\n")
    printf(p1 "subckt %s (%s)\n" CELL portString)
  )
  when(p2 printf(p2 "inst,master_lib,master_cell,model,l_expr,w_expr,D,G,S,B\n"))

  nMOS = 0
  foreach(obj dbGet(cv "instances")
    mdl = dbGet(obj "model")
    when(mdl
      nMOS = nMOS + 1
      nm = dbGet(obj "name")
      lE = nlPropVal(obj "l")
      wE = nlPropVal(obj "simW")
      dN = nlNetOfTerm(obj "D")
      gN = nlNetOfTerm(obj "G")
      sN = nlNetOfTerm(obj "S")
      bN = nlNetOfTerm(obj "B")
      printf("NL-ROW %L %L/%L %L l=%L w=%L (%L %L %L %L)\n" nm
             dbGet(dbGet(obj "master") "libName") dbGet(dbGet(obj "master") "cellName")
             mdl lE wE dN gN sN bN)
      when(p2
        printf(p2 "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" nm
               dbGet(dbGet(obj "master") "libName") dbGet(dbGet(obj "master") "cellName")
               mdl lE wE dN gN sN bN)
      )
      when(p1
        printf(p1 "  %s (%s %s %s %s) %s l=%s w=%s\n" nm dN gN sN bN mdl lE wE)
      )
    )
  )
  printf("NL-MOS-ROWS %L\n" nMOS)
  printf("NL-INST-TOTAL %L\n" length(dbGet(cv "instances")))
  printf("NL-NET-TOTAL %L\n" length(dbGet(cv "nets")))
  when(p1
    printf(p1 "ends %s\n" CELL)
    close(p1)
  )
  when(p2 close(p2))
  printf("NL-WROTE %L\n" NLPATH)
  printf("NL-WROTE %L\n" CSVPATH)
  errset(printf("NL-CHECK %L\n" dbCheck(cv)))
  errset(printf("NL-SAVE %L\n" dbSave(cv)))
  dbClose(cv)
)
printf("NL_DONE\n")
exit()
