;; R2 OA readback (READ ONLY): per-terminal instance-to-net connectivity and
;; symbol terminals. Proves the saved schematic's electrical connections without
;; opening anything for write and without touching any PDK or existing library.
;; Run: dbAccess -load course_oa_readback2.il
printf("COURSE_OA2_BEGIN\n")
o2Lib = "course_sim_20261112"

procedure(o2Val(v) if(v v "NONE"))

foreach(o2Cell list("course_sink_unit" "course_sink_top")
  o2cv = car(errset(dbOpenCellViewByType(o2Lib o2Cell "schematic" nil "r")))
  o2op = "NO"
  when(o2cv o2op = "YES")
  printf("COURSE_OA2_CELL %L opened=%L\n" o2Cell o2op)
  when(o2cv
    o2inst = car(errset(dbGet(o2cv "instances")))
    o2net = car(errset(dbGet(o2cv "nets")))
    o2ni = 0
    when(o2inst o2ni = length(o2inst))
    o2nn = 0
    when(o2net o2nn = length(o2net))
    printf("COURSE_OA2_COUNTS %L inst=%L net=%L\n" o2Cell o2ni o2nn)
    foreach(o2i o2inst
      o2iname = o2Val(car(errset(dbGet(o2i "name"))))
      o2ilib = o2Val(car(errset(dbGet(o2i "libName"))))
      o2icell = o2Val(car(errset(dbGet(o2i "cellName"))))
      printf("COURSE_OA2_INST %L %L master=%L/%L\n" o2Cell o2iname o2ilib o2icell)
      o2t = car(errset(dbGet(o2i "instTerms")))
      when(o2t
        foreach(o2tt o2t
          o2tname = o2Val(car(errset(dbGet(o2tt "name"))))
          o2n = car(errset(dbGet(o2tt "net")))
          o2nname = "NONE"
          when(o2n
            o2tmp = car(errset(dbGet(o2n "name")))
            when(o2tmp o2nname = o2tmp)
          )
          printf("COURSE_OA2_TERM %L %L.%L -> %L\n" o2Cell o2iname o2tname o2nname)
        )
      )
    )
    errset(dbClose(o2cv))
  )
  o2sym = car(errset(dbOpenCellViewByType(o2Lib o2Cell "symbol" nil "r")))
  o2sop = "NO"
  when(o2sym o2sop = "YES")
  printf("COURSE_OA2_SYMBOL %L opened=%L\n" o2Cell o2sop)
  when(o2sym
    o2terms = car(errset(dbGet(o2sym "terminals")))
    when(o2terms
      foreach(o2s o2terms
        o2sname = o2Val(car(errset(dbGet(o2s "name"))))
        o2sdir = o2Val(car(errset(dbGet(o2s "direction"))))
        printf("COURSE_OA2_SYMTERM %L %L dir=%L\n" o2Cell o2sname o2sdir)
      )
    )
    errset(dbClose(o2sym))
  )
)
printf("COURSE_OA2_END\n")
