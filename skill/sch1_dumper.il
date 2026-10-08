; SCH-1 diagnostic: find the attribute under which this build exposes a cellview's terminals.
;
; Why: length(nil) == 0 in SKILL, so every "terms=0" printed so far was ambiguous -- it could
; mean an empty terminal list or an attribute name that does not exist. The control settles it:
; smic18mmrf/p18:symbol provably HAS terminals (the instance terminals in our schematic resolve
; to names D/G/S/B), so whichever attribute of that master returns them is the right accessor.
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_dumper.il 420 DM_DONE
printf("DM-BEGIN\n")
NAMES = list("terms" "allTerms" "termViews" "termList" "bTerms" "pins" "pinFigs" "figures" "figs"
             "labels" "props" "propNames" "nets" "insts" "instances" "shapes" "instHeaders"
             "mosaics" "hierTerms" "switchTerms" "termObjs" "cellViews" "name" "cellName"
             "libName" "viewName" "viewType" "objType" "techLib" "cell" "master")

procedure(dmDump(obj tag)
  let((vv)
    printf("DM-DUMP %s obj=%L objType=%L\n" tag obj errset(dbGet(obj "objType")))
    foreach(nm NAMES
      vv = errset(dbGet(obj nm))
      printf("DM-%s %L => %L\n" tag nm vv)
    )
  )
)

cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv
  mos = car(dbGet(cv "instances"))
  mst = dbGet(mos "master")
  dmDump(cv "CV")
  dmDump(mst "MASTER")
  it0 = car(dbGet(mos "instTerms"))
  dmDump(it0 "ISTERM")
  dmDump(dbGet(it0 "term") "TERM")
  foreach(i dbGet(cv "instances")
    printf("DM-INST %L master=%L/%L:%L\n" dbGet(i "name") errset(dbGet(dbGet(i "master") "libName"))
           errset(dbGet(dbGet(i "master") "cellName")) errset(dbGet(dbGet(i "master") "viewName")))
  )
  dbClose(cv)
)
printf("DM_DONE\n")
exit()
