; SCH-2 Part A: back up the current schematic with an OA-supported copy before anything is touched.
;
; dbCopyCellView is the OpenAccess copy primitive, so the backup is a real cellview the tool can
; open -- not a file copy that could split a half-written transaction. The source is opened READ
; ONLY and stays open across the copy; the operator's GUI session still holds the write lock on
; c2mos_dff_1bit/schematic, so this file never opens that cellview in a writable mode.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch2_backup.il 400 BK_DONE
printf("BK-BEGIN\n")

LIB = "microled_cells"
SRC_CELL = "c2mos_dff_1bit"
DST_CELL = "c2mos_dff_1bit_pre_paramfix"

procedure(bkCount(cv tag)
  let((ni nn ns)
    ni = length(dbGet(cv "instances"))
    nn = length(dbGet(cv "nets"))
    ns = length(dbGet(cv "shapes"))
    printf("BK-COUNT %L instances=%L nets=%L shapes=%L\n" tag ni nn ns)
  )
)

src = dbOpenCellViewByType(LIB SRC_CELL "schematic" "schematic" "r")
unless(src
  printf("BK-SOURCE-OPEN-FAILED\n")
)
when(src
  bkCount(src "SOURCE")
  ; form 1: (srcCellView lib cell view)
  r1 = errset(dbCopyCellView(src LIB DST_CELL "schematic"))
  printf("BK-COPY-FORM1 %L\n" r1)
  unless(car(r1)
    ; form 2: create the destination cellview first, then copy into it
    dst = errset(dbOpenCellViewByType(LIB DST_CELL "schematic" "schematic" "w"))
    printf("BK-DST-CREATE %L\n" dst)
    when(dst
      printf("BK-COPY-FORM2 %L\n" errset(dbCopyCellView(src dst)))
      dbClose(dst)
    )
  )
  dbClose(src)
)

chk = dbOpenCellViewByType(LIB DST_CELL "schematic" "schematic" "r")
when(chk
  printf("BK-BACKUP-OPENS %s/%s\n" LIB DST_CELL)
  bkCount(chk "BACKUP")
  dbClose(chk)
,
  printf("BK-BACKUP-OPEN-FAILED\n")
)
printf("BK_DONE\n")
exit()
