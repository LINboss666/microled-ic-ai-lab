; SCH-1 Part C/D finalize: give the ASG-generated cellview its real ports, run the database
; checker, save, and dump what the cellview contains afterwards. Port names come from the
; generated table (scripts/sch1_gen_ports.py reads them out of the accepted golden netlist);
; nothing in this file lists an instance, a net or a pin of the DFF by hand.
;
; dbCreateTerm( net name direction ) is the documented primitive for a cellview port; it attaches
; the terminal to the net that the checker already bound, so the pin cannot disagree with the
; connectivity that is in the database.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_finalize.il 400 FZ_DONE
printf("FZ-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")

LIB = "microled_cells"
CELL_ENV = getShellEnvVar("SCH1_CELL")
CELL = if(CELL_ENV CELL_ENV "c2mos_dff_1bit")

procedure(fzFindNet(theCv name)
  let((found)
    found = nil
    foreach(n dbGet(theCv "nets")
      if(dbGet(n "name") == name found = n)
    )
    found
  )
)

cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
when(cv
  printf("FZ-OPENED %s/%s\n" LIB CELL)
  errset(printf("FZ-CHECK-BEFORE %L\n" dbCheck(cv)))
  foreach(entry sch1PortTable
    let((net made)
      net = fzFindNet(cv car(entry))
      printf("FZ-LOOKUP %L => %L\n" car(entry) if(net "net-found" "NET-MISSING"))
      when(net
        made = errset(dbCreateTerm(net car(entry) cadr(entry)))
        printf("FZ-PIN %L %L => %L\n" car(entry) cadr(entry) made)
      )
    )
  )
  errset(printf("FZ-CHECK-AFTER %L\n" dbCheck(cv)))
  errset(printf("FZ-SAVE %L\n" dbSave(cv)))
  errset(printf("FZ-TECH %L\n" techGetTechFile(cv)))
  errset(printf("FZ-TECH-CELL %L\n" techGetTechFile(dbGet(cv "cell"))))
  dbClose(cv)
,
  printf("FZ-OPEN-FAILED\n")
)

cv2 = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
when(cv2
  printf("FZ-REOPENED\n")
  errset(printf("FZ-SUMMARY instances=%L nets=%L terms=%L shapes=%L\n"
                 length(dbGet(cv2 "instances")) length(dbGet(cv2 "nets"))
                 length(dbGet(cv2 "terms")) length(dbGet(cv2 "shapes"))))
  foreach(t dbGet(cv2 "terms")
    errset(printf("FZ-TERM %L %L net=%L\n" dbGet(t "name") dbGet(t "direction")
                   if(dbGet(t "net") dbGet(dbGet(t "net") "name") "-")))
  )
  dbClose(cv2)
)
printf("FZ_DONE\n")
exit()
