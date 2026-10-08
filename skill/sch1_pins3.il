; SCH-1 Part C, ports attempt 3 (last one under the three-try rule).
;
; Attempt 3a tried dbOpenCellViewByType on the masters and both smic18mmrf/p18:symbol and
; basic/iopin:symbol came back nil, even though instances of exactly those masters sit in our
; cellview. The master handles are therefore taken from the existing instances (inst->master),
; which is how the database itself exposes them. That also gives the control reading this run
; needs: if p18's master reports its four terminals through the same "terms" accessor, the
; accessor is correct and an empty cv->terms means the ports were really not saved.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_pins3.il 420 P3_DONE
printf("P3-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(p3FindNet(theCv name)
  let((found)
    found = nil
    foreach(n dbGet(theCv "nets")
      if(dbGet(n "name") == name found = n)
    )
    found
  )
)

procedure(p3FindInst(theCv name)
  let((found)
    found = nil
    foreach(i dbGet(theCv "instances")
      if(dbGet(i "name") == name found = i)
    )
    found
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  printf("P3-OPENED\n")
  mos = car(dbGet(cv "instances"))
  mmos = dbGet(mos "master")
  printf("P3-CONTROL-MASTER %L lib=%L cell=%L view=%L terms=%L\n" mmos
         errset(dbGet(mmos "libName")) errset(dbGet(mmos "cellName"))
         errset(dbGet(mmos "viewName")) errset(length(dbGet(mmos "terms"))))
  foreach(t errset(dbGet(mmos "terms"))
    printf("P3-CONTROL-TERM %L %L\n" errset(dbGet(t "name")) errset(dbGet(t "direction")))
  )
  io0 = p3FindInst(cv "PIN0")
  printf("P3-PIN0-INST %L master=%L\n" io0 errset(dbGet(io0 "master")))
  iopm = if(io0 dbGet(io0 "master") nil)
  printf("P3-IOPIN-MASTER %L terms=%L\n" iopm errset(length(dbGet(iopm "terms"))))

  when(iopm
    foreach(n list(0 1 2 3 4 5)
      entry = nth(n sch1PortTable)
      let((net fig pin)
        net = p3FindNet(cv car(entry))
        when(net
          fig = errset(dbCreateInst(cv iopm sprintf(nil "PIN_%s" car(entry)) list(n * 4 12)))
          pin = errset(if(fig dbCreatePin(net fig car(entry)) nil))
          printf("P3-PIN %L fig=%L pin=%L\n" car(entry) fig pin)
        )
      )
    )
  )
  errset(printf("P3-CHECK %L\n" dbCheck(cv)))
  printf("P3-TERMS-MID %L INSTS-MID %L\n" length(dbGet(cv "terms")) length(dbGet(cv "instances")))
  errset(printf("P3-SAVE %L\n" dbSave(cv)))
  dbClose(cv)
)

cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv2
  printf("P3-REOPENED SUMMARY instances=%L nets=%L terms=%L shapes=%L\n"
         length(dbGet(cv2 "instances")) length(dbGet(cv2 "nets"))
         length(dbGet(cv2 "terms")) length(dbGet(cv2 "shapes")))
  foreach(t dbGet(cv2 "terms")
    printf("P3-TERM %L %L net=%L\n" dbGet(t "name") dbGet(t "direction")
           if(dbGet(t "net") dbGet(dbGet(t "net") "name") "-"))
  )
  dbClose(cv2)
)
printf("P3_DONE\n")
exit()
