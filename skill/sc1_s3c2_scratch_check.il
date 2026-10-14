;; sc1_s3c2_scratch_check.il
;;
;; Which net does each instance terminal carry AFTER the re-lay, in this round's scratch cellview?
;; The loop test drew the internal gate33 segment and, after save and reopen, that figure reports its
;; net as an auto name (net11). The question is not cosmetic: either the two pins still carry gate33
;; and the new wire is electrically adrift, or the pins moved to the auto name and the topology
;; survived under a changed label. Only the terminals can say, so this file reads them from disk.
;; SKILL protects the variable t, so the loop names are tm2/tm3 (measured in S3C1).
;; Read-only: mode "r". NEW_SIMULATION_RUNS = 0.

kcLib = "microled_scan_s3c"
kcCell = "s3c2_loop_top"

procedure(kcVal(v)
  if(v == nil "NONE" v)
)

printf("KC-BEGIN\n")
cv = car(errset(dbOpenCellViewByType(kcLib kcCell "schematic" "schematic" "r")))
printf("KC-OPEN %L shapes=%L nets=%L insts=%L\n" cv != nil length(cv~>shapes) length(cv~>nets)
       length(cv~>instances))
foreach(n cv~>nets
  printf("KC-NET %L\n" kcVal(n~>name))
)
foreach(i cv~>instances
  when(i~>cellName != "iopin"
    foreach(tm2 i~>instTerms
      printf("KC-TERM %L %L %L net=%L\n" i~>cellName i~>name tm2~>name
             kcVal(if(tm2~>net tm2~>net~>name nil)))
    )
  )
)
foreach(f cv~>shapes
  when(equal(f~>layerName "wire")
    when(equal(f~>purpose "drawing")
      printf("KC-WIRE net=%L bbox=%L\n" kcVal(if(f~>net f~>net~>name nil)) f~>bBox)
    )
  )
)
foreach(tm3 cv~>terminals
  printf("KC-VTERM %L net=%L pins=%L\n" tm3~>name kcVal(if(tm3~>net tm3~>net~>name nil))
         length(tm3~>pins))
)
printf("KC-DONE\n")
nil
