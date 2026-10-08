printf("B4-BEGIN\n")
cv = dbOpenCellViewByType("microled_cells" "c2mos_dff_1bit" "schematic" "schematic" "r")
foreach(spec list(
   "length(list(1 2))"
   "cv->viewType"
   "cv->insts"
   "length(cv->insts)"
   "length(setof(i cv->insts t))"
   "getattr(cv \"viewType\")"
   "dbGetAttr(cv \"viewType\")"
   "dbGetAttr(cv 'viewType)"
   "cv~\"viewType\""
   "cv ~ viewType"
   "cv~viewType "
   "dbGetCellViewName(cv)"
   "cv->name"
   )
  r = errset(loadstring(spec))
  printf("B4-LS [%s] => %L\n" spec r)
)
printf("B4_DONE\n")
exit()
