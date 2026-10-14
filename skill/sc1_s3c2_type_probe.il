;; sc1_s3c2_type_probe.il
;;
;; One read-only question, asked because the write pass could not find the port name displays:
;; what TYPES do these attributes have, and does an equal() against a literal match? S3C1 measured
;; that objType/purpose read back as strings, but %L prints a string and a symbol identically, so
;; the earlier log could not show why the comparison failed. This file prints type() itself plus the
;; outcome of each candidate comparison, so the next write pass is written from evidence.
;; Read-only: mode "r", nothing saved. NEW_SIMULATION_RUNS = 0.

tpLib = "microled_scan_s3c"
tpCell = "s3c2_loop_top"

procedure(tpT(v)
  if(v == nil "nil" type(v))
)

printf("TP-BEGIN\n")
cv = car(errset(dbOpenCellViewByType(tpLib tpCell "schematic" "schematic" "r")))
printf("TP-OPEN %L\n" cv != nil)
n = 0
foreach(f cv~>shapes
  n = n + 1
  when(lessp(n 6)
    printf("TP-SHAPE %L objType=%L type=%L lpp=%L/%L xy=%L xytype=%L xtype=%L\n" n f~>objType
           tpT(f~>objType) f~>layerName f~>purpose f~>xy tpT(f~>xy) tpT(car(f~>xy)))
    printf("TP-CMP %L eq-string=%L eq-symbol=%L eq-xy=%L neq-xy=%L\n" n
           equal(f~>objType "textDisplay") equal(f~>objType 'textDisplay)
           equal(car(f~>xy) 6.625) equal(car(f~>xy) 6.626))
  )
)
printf("TP-COUNT %L\n" n)
printf("TP-DONE\n")
nil
