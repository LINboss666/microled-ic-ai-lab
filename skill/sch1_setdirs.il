; SCH-1: the six terminals exist but report direction "unused" -- dbCreatePin(net fig name) with
; no term argument re-made the terminal with a default direction, overriding what dbCreateTerm
; was asked for. Try the documented setter, save, and read the directions back from disk.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_setdirs.il 300 SD_DONE
printf("SD-BEGIN\n")
load("/root/microled_ai_project/skill/sch1_ports.gen.il")
printf("SD-HAVE-dbSetTermDirection %L\n" getd('dbSetTermDirection))
cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "a")
when(cv
  foreach(entry sch1PortTable
    let((term)
      term = errset(dbFindTermByName(cv car(entry)))
      when(term
        printf("SD-SET %L %L => %L\n" car(entry) cadr(entry)
               errset(dbSetTermDirection(term cadr(entry))))
      )
    )
  )
  errset(printf("SD-CHECK %L\n" dbCheck(cv)))
  errset(printf("SD-SAVE %L\n" dbSave(cv)))
  dbClose(cv)
)
cv2 = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv2
  foreach(entry sch1PortTable
    let((term)
      term = errset(dbFindTermByName(cv2 car(entry)))
      printf("SD-BACK %L %L\n" car(entry) if(term errset(dbGet(term "direction")) "NO-TERM"))
    )
  )
  dbClose(cv2)
)
printf("SD_DONE\n")
exit()
