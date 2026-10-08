; SCH-1 Part C, ports attempt 3.
;
; Attempts 1 and 2 used dbCreateTerm(net name direction) and dbCreatePin(net nil name). Both
; returned live objects, and both were gone from the saved database: the cellview still reported
; zero terms. This attempt copies what Cadence's own importer did -- it created an instance of
; basic/iopin:symbol as the pin figure -- by giving every port a real iopin figure before the pin
; is attached to it. The iopin master is opened from the same cds.lib the GUI uses, so the port
; objects are built from library masters, not from a hand-drawn symbol.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_pins2.il 420 P2_DONE
printf("P2-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(p2FindNet(theCv name)
  let((found)
    found = nil
    foreach(n dbGet(theCv "nets")
      if(dbGet(n "name") == name found = n)
    )
    found
  )
)

iop = dbOpenCellViewByType("basic" "iopin" "symbol" "symbol" "r")
printf("P2-IOPIN-MASTER %L\n" iop)
when(iop
  printf("P2-IOPIN-TERMS %L\n" length(dbGet(iop "terms")))
  foreach(t dbGet(iop "terms")
    printf("P2-IOPIN-TERM %L %L\n" dbGet(t "name") dbGet(t "direction"))
  )
)
sym = dbOpenCellViewByType("smic18mmrf" "p18" "symbol" "symbol" "r")
printf("P2-CONTROL-P18 %L\n" sym)
when(sym
  printf("P2-CONTROL-P18-TERMS %L\n" length(dbGet(sym "terms")))
  dbClose(sym)
)

when(iop
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
  when(cv
    printf("P2-OPENED %s/%s\n" LIB CELL)
    printf("P2-INSTS-BEFORE %L TERMS-BEFORE %L\n" length(dbGet(cv "instances"))
                                             length(dbGet(cv "terms")))
    foreach(n list(0 1 2 3 4 5)
      entry = nth(n sch1PortTable)
      let((net fig pin)
        net = p2FindNet(cv car(entry))
        when(net
          fig = errset(dbCreateInst(cv iop sprintf(nil "PIN_%s" car(entry)) list(n * 4 12)))
          pin = errset(if(fig dbCreatePin(net fig car(entry)) nil))
          printf("P2-PIN %L fig=%L pin=%L\n" car(entry) fig pin)
        )
      )
    )
    errset(printf("P2-CHECK %L\n" dbCheck(cv)))
    printf("P2-TERMS-MID %L\n" length(dbGet(cv "terms")))
    errset(printf("P2-SAVE %L\n" dbSave(cv)))
    dbClose(cv)
  )
  dbClose(iop)
)

cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv2
  printf("P2-REOPENED\n")
  printf("P2-SUMMARY instances=%L nets=%L terms=%L shapes=%L\n"
         length(dbGet(cv2 "instances")) length(dbGet(cv2 "nets"))
         length(dbGet(cv2 "terms")) length(dbGet(cv2 "shapes")))
  foreach(t dbGet(cv2 "terms")
    printf("P2-TERM %L %L net=%L\n" dbGet(t "name") dbGet(t "direction")
           if(dbGet(t "net") dbGet(dbGet(t "net") "name") "-"))
  )
  dbClose(cv2)
)
printf("P2_DONE\n")
exit()
