;; Course OA readback (READ ONLY): proves the newly created course library really
;; holds saved schematic objects with instances, nets and terminals.
;; No PDK object is opened for write; no existing OA library is touched.
;; Run with: dbAccess -load course_oa_readback.il
printf("COURSE_OA_READBACK_BEGIN\n")
coLib = "course_sim_20261112"

procedure(coVal(v) if(v v "NONE"))
procedure(coLen(x) if(x length(x) 0))

coCells = list("course_sink_unit" "course_sink_top")
foreach(coCell coCells
  cv = car(errset(dbOpenCellViewByType(coLib coCell "schematic" nil "r")))
  printf("COURSE_OA_CELL %L opened=%L\n" coCell (cv != nil))
  when(cv
    insts = car(errset(dbGet(cv "instances")))
    nets  = car(errset(dbGet(cv "nets")))
    terms = car(errset(dbGet(cv "terminals")))
    shapes = car(errset(dbGet(cv "shapes")))
    printf("COURSE_OA_COUNTS cell=%L instances=%L nets=%L terminals=%L shapes=%L\n"
           coCell coLen(insts) coLen(nets) coLen(terms) coLen(shapes))
    foreach(n nets
      printf("COURSE_OA_NET %L %L\n" coCell coVal(car(errset(dbGet(n "name"))))))
    foreach(i insts
      printf("COURSE_OA_INST %L name=%L masterCell=%L masterLib=%L\n"
             coCell coVal(car(errset(dbGet(i "name"))))
             coVal(car(errset(dbGet(i "cellName"))))
             coVal(car(errset(dbGet(i "libName"))))))
    foreach(t terms
      printf("COURSE_OA_TERM %L %L\n" coCell coVal(car(errset(dbGet(t "name"))))))
    errset(dbClose(cv))
  )
)
printf("COURSE_OA_READBACK_END\n")
