; SCH-1 Part C: give the cellview real ports, and find out which accessor actually reports them.
;
; Two documented primitives were available in batch: dbCreateTerm(net name direction) and
; dbCreatePin(net fig|nil name [term]). dbCreateTerm alone did NOT survive -- after dbSave the
; cellview still reported no terms -- so this run uses dbCreatePin (the pin object is what the
; editor shows and what the netlister treats as a port) and re-reads everything from the saved
; database. The p18 symbol is opened as a control: if its terminal list also reads back empty,
; the accessor name is wrong; if it does not, the accessor is right and our cell is the thing
; that was missing.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_pins.il 400 PN_DONE
printf("PN-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(pnFindNet(theCv name)
  let((found)
    found = nil
    foreach(n dbGet(theCv "nets")
      if(dbGet(n "name") == name found = n)
    )
    found
  )
)

sym = dbOpenCellViewByType("smic18mmrf" "p18" "symbol" "symbol" "r")
when(sym
  printf("PN-CONTROL p18:symbol terms=%L names=%L\n" length(dbGet(sym "terms"))
         errset(mapcar(lambda((t) dbGet(t "name")) dbGet(sym "terms"))))
  dbClose(sym)
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  printf("PN-OPENED %s/%s\n" LIB CELL)
  printf("PN-TERMS-BEFORE %L\n" length(dbGet(cv "terms")))
  foreach(entry sch1PortTable
    let((net made)
      net = pnFindNet(cv car(entry))
      when(net
        made = errset(dbCreatePin(net nil car(entry)))
        printf("PN-CREATEPIN %L %L => %L\n" car(entry) cadr(entry) made)
      )
    )
  )
  printf("PN-TERMS-MID %L\n" length(dbGet(cv "terms")))
  errset(printf("PN-CHECK %L\n" dbCheck(cv)))
  errset(printf("PN-SAVE %L\n" dbSave(cv)))
  dbClose(cv)
)

cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv2
  printf("PN-REOPENED\n")
  printf("PN-SUMMARY instances=%L nets=%L terms=%L shapes=%L\n"
         length(dbGet(cv2 "instances")) length(dbGet(cv2 "nets"))
         length(dbGet(cv2 "terms")) length(dbGet(cv2 "shapes")))
  foreach(t dbGet(cv2 "terms")
    printf("PN-TERM %L %L net=%L\n" dbGet(t "name") dbGet(t "direction")
           if(dbGet(t "net") dbGet(dbGet(t "net") "name") "-"))
  )
  dbClose(cv2)
)
printf("PN_DONE\n")
exit()
