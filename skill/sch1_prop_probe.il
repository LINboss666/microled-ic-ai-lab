; SCH-1: where do the transistor sizes live on the instances ASG created?
;
; Without them the schematic is not electrically complete, so this is looked for before anything
; is claimed. Both the documented property functions (dbFindProp / dbGetPropByName) and a sweep of
; attribute names on one instance are tried, and every candidate prop name is read on two
; instances that are supposed to have DIFFERENT widths (a clocked device and a keeper device).
;
; Run: bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch1_prop_probe.il 300 PP_DONE
printf("PP-BEGIN\n")
printf("PP-HAVE-dbFindProp %L\n" getd('dbFindProp))
printf("PP-HAVE-dbGetPropByName %L\n" getd('dbGetPropByName))
printf("PP-HAVE-dbGetParam %L\n" getd('dbGetParam))
printf("PP-HAVE-dbSetParam %L\n" getd('dbSetParam))
printf("PP-HAVE-dbReplaceParam %L\n" getd('dbReplaceParam))
cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
when(cv
  foreach(nm list("params" "paramList" "properties" "props" "propList" "instParams" "pcellParams"
                  "formValues" "parameterValues")
    printf("PP-ATTR %L => %L\n" nm errset(dbGet(car(dbGet(cv "instances")) nm)))
  )
  foreach(entry list(list("mp_c" "wcp") list("mn_k1" "wk"))
    inst = nil
    foreach(i dbGet(cv "instances")
      if(dbGet(i "name") == car(entry) inst = i)
    )
    when(inst
      foreach(pn list("w" "l" "m" "W" "L" "simW" "simL" "model" "cellModel")
        printf("PP-PROP %L %L => %L\n" car(entry) pn
               errset(dbGet(dbFindProp(inst pn) "value")))
      )
    )
  )
  dbClose(cv)
)
printf("PP_DONE\n")
exit()
