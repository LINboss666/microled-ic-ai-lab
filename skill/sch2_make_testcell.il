; SCH-2 Part E step 0: give the fix experiment its own cellview.
;
; c2mos_dff_1bit stays untouched (the operator's GUI still holds its write lock) and
; c2mos_dff_1bit_pre_paramfix stays as the untouched backup. The experiment runs on a copy of the
; backup, so every number measured after the fix can be attributed to the fix alone.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch2_make_testcell.il 500 TC_DONE
printf("TC-BEGIN\n")
LIB = "microled_cells"
SRC = "c2mos_dff_1bit_pre_paramfix"
DST = "c2mos_dff_1bit_paramfix"

already = car(errset(dbOpenCellViewByType(LIB DST "schematic" nil "r")))
when(already
  printf("TC-REFUSE %s/%s already exists -- nothing is overwritten\n" LIB DST)
  dbClose(already)
)
unless(already
  src = dbOpenCellViewByType(LIB SRC "schematic" nil "r")
  when(src
    printf("TC-SUMMARY-SOURCE instances=%L nets=%L shapes=%L\n" length(dbGet(src "instances"))
           length(dbGet(src "nets")) length(dbGet(src "shapes")))
    r = errset(dbCopyCellView(src LIB DST "schematic"))
    printf("TC-COPY %L\n" r)
    dbClose(src)
  )
)

chk = dbOpenCellViewByType(LIB DST "schematic" nil "r")
when(chk
  printf("TC-TESTCELL-OPENS instances=%L nets=%L shapes=%L\n" length(dbGet(chk "instances"))
         length(dbGet(chk "nets")) length(dbGet(chk "shapes")))
  dbClose(chk)
)
unless(chk
  printf("TC-TESTCELL-MISSING\n")
)
printf("TC_DONE\n")
exit()
