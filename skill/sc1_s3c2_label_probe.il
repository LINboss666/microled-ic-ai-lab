;; sc1_s3c2_label_probe.il
;;
;; One read-only question, asked because section 6 forbids reading a nil as "the label text is
;; there": which attribute of a label figure in THIS build carries the string? The dump has always
;; printed ~>text and for every label -- the importer's own and the ones this round created -- it
;; returns nil, while ~>justification on a Symbol pin label reads back fine. Candidates are printed
;; by name, and dbShow is asked for the object's own property list if this build has it.
;; Target is this round's scratch cellview (saved by the loop test), opened in mode "r".
;; NEW_SIMULATION_RUNS = 0. Nothing is written.

lpLib = "microled_scan_s3c"
lpCell = "s3c2_loop_top"

procedure(lpVal(v)
  if(v == nil "NONE" v)
)

procedure(lpAttrs(o)
  printf("LP-OBJ objType=%L text=%L strings=%L val=%L label=%L name=%L objName=%L just=%L\n"
         lpVal(o~>objType) lpVal(s2wGet(o 'text)) lpVal(s2wGet(o 'strings))
         lpVal(s2wGet(o 'val)) lpVal(s2wGet(o 'label)) lpVal(s2wGet(o 'name))
         lpVal(s2wGet(o 'objName)) lpVal(s2wGet(o 'justification)))
)

procedure(s2wGet(o nm)
  car(errset(dbGet(o nm)))
)

printf("LP-BEGIN\n")
printf("LP-DBSHOW-EXISTS %L\n" getd('dbShow) != nil)
cv = car(errset(dbOpenCellViewByType(lpLib lpCell "schematic" "schematic" "r")))
printf("LP-OPEN %L shapes=%L nets=%L\n" cv != nil length(cv~>shapes) length(cv~>nets))
n = 0
foreach(f cv~>shapes
  when(equal(f~>objType "label")
    n = n + 1
    when(lessp(n 4)
      printf("LP-WIRE-LABEL %L net=%L xy=%L\n" n lpVal(if(f~>net f~>net~>name nil))
             lpVal(s2wGet(f 'xy)))
      lpAttrs(f)
    )
  )
)
printf("LP-WIRE-LABEL-COUNT %L\n" n)
printf("LP-DONE\n")
nil
