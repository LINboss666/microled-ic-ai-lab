;; sc1_s3c2_ciw_parents.il
;;
;; What this is: the two hierarchy parents this round could NOT re-lay safely
;; (sc1_ls_c1_top_r2d, sc1_r3_scan_chain_1ch) are left at their pre-S3C2 geometry, and their
;; sub-instance pins therefore still sit at the wire ends the netlist importer drew before the
;; Symbol pin placement. Task book section 7 asks for a short script the user can run in an already
;; open CIW instead of another batch probe round, so this file prints the plan and says what to do;
;; it changes nothing by itself.
;;
;; Read this first (measured, results/evidence/sc1_s3c2_log_relay_attempt_errors.txt and
;; ..._relay_keep_attempt_errors.txt and ..._relay_stub_attempt_errors.txt): for both views the
;; re-lay was applied on a copy and on the delivered view and schCheck answered
;;   Error: Terminal "vdd18" shorted to terminal "blank".
;;   Error: Terminal "vdd18" shorted to terminal "core_ok33".
;;   Error: (DB-270004): Illegal bus reference - Can't tap "<vdd18>" from net "core_ok33".
;; for the chain, and the vdd33 equivalent for sc1_ls_c1_top_r2d, in all three strategies
;; (stubs+labels, kept-unchanged wires, outward-facing port stubs). The view was then restored from
;; backup_microled_scan_s3c_pre_s3c2_20261014.tgz and the restore verified by md5 against
;; cadence_work/s3c_oa/logs/pre_s3c2_lib.md5. So the blocker is the drawing plan, not the API: the
;; rails cannot be laid in the band between the blocks and the port rows without crossing a signal
;; route, and crossing wires are connected in Virtuoso.
;;
;; To finish it by hand in the GUI: open the schematic, drag the three/four blocks apart enough to
;; free a rail lane, route vdd18/vdd33/vss as rails, then Check and Save (the SCH-2162 warning
;; clears on the first Check and Save, and section 5 requires handling it per case, which is what
;; this does -- it is a "the Symbol view is newer than this schematic's last save" notice, and the
;; pins it warns about have been re-connected and re-read in the delivered top-level view).
;;
;; NEW_SIMULATION_RUNS = 0. This file performs no write and no save.

cpLib = "microled_scan_s3c"
cpCells = list("sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch")

printf("S3C2CIW-BEGIN\n")
foreach(cell cpCells
  cv = car(errset(dbOpenCellViewByType(cpLib cell "schematic" "schematic" "r")))
  printf("S3C2CIW %L open=%L shapes=%L insts=%L nets=%L\n" cell cv != nil length(cv~>shapes)
         length(cv~>instances) length(cv~>nets))
  foreach(i cv~>instances
    when(i~>cellName != "iopin"
      foreach(t i~>instTerms
        printf("S3C2CIW-PIN %L %L %L %L net=%L\n" cell i~>name i~>cellName t~>name
               if(t~>net t~>net~>name "NO_NET"))
      )
    )
  )
  foreach(t cv~>terminals
    printf("S3C2CIW-PORT %L %L %L net=%L\n" cell t~>name t~>direction
           if(t~>net t~>net~>name "NO_NET"))
  )
  dbClose(cv)
)
printf("S3C2CIW-HINT load(asg_in/s3c2_lsc1_relay.il) applies the printed plan and reports schCheck;
")
printf("S3C2CIW-HINT run it on a copy first: dbCopyCellView, then apply to the copied cell name\n")
printf("S3C2CIW-DONE\n")
nil
