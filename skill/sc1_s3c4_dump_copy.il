;; sc1_s3c4_dump_copy.il -- dump the copy of the top Symbol with the shared read-only inventory.
;;
;; The copy-first proof (S3C4 task book: repair on a copy of one target Symbol and read it back before
;; touching the rest) needs the same columns as the BEFORE dump, so this only pre-sets the cell list;
;; sc1_s3c4_dump_symbols.il keeps its own default list for the real views and honours sdCells when a
;; caller already set it. Reads only, mode "r", NEW_SIMULATION_RUNS = 0.

sdCells = list("s3c4_top_sym_copy")
load("/root/microled_ai_project/cadence_work/s3c_oa/sc1_s3c4_dump_symbols.il")
nil
