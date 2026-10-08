; SCH-1: are the six ports actually in the saved database?
;
; The doc for connect.html gives dbFindTermByName(cellView name) and the Net attribute "pins", so
; terminals can be looked up directly instead of through a cellview attribute whose name was a
; guess. Everything printed here is a lookup against the saved cellview.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_verify_ports.il 300 VP_DONE
printf("VP-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")
cv = dbOpenCellViewByType("microled_cells" CELL "schematic" "schematic" "r")
when(cv
  foreach(entry sch1PortTable
    let((term net pins dir)
      term = errset(dbFindTermByName(cv car(entry)))
      net = errset(dbFindNetByName(cv car(entry)))
      pins = if(net errset(dbGet(net "pins")) nil)
      dir = if(term errset(dbGet(term "direction")) nil)
      printf("VP-PORT %L term=%L net=%L netPins=%L direction=%L\n" car(entry) term net pins dir)
    )
  )
  printf("VP-NET-PINS-ALL\n")
  foreach(n dbGet(cv "nets")
    printf("VP-NET %L pins=%L\n" errset(dbGet(n "name")) errset(dbGet(n "pins")))
  )
  dbClose(cv)
)
printf("VP_DONE\n")
exit()
