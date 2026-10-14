; SCAN-1 S3-C section 3: create THIS TASK's OA library, refuse to touch anything that exists.
;
; hiCreateDirLib is the call SCH-1 measured on this build (it produced cadence_work/microled_cells
; with its tech.db). Here the library name is resolved through this task's own cds.lib, so the
; directory lands under cadence_work/s3c_oa and no existing library is reopened for write.
;
; The guard is a refusal, not an overwrite: if the library is already there the file prints its
; path and stops creating. It never deletes, never re-registers, never writes a cell.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c_mklib.il 300 MKLIB_DONE
printf("S3CMK-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
printf("S3CMK-LIB %L\n" LIB)

existing = errset(ddGetObj(LIB))
printf("S3CMK-ALREADY %L\n" existing)
when(existing == nil
  printf("S3CMK-CREATE %L\n" errset(hiCreateDirLib(LIB)))
)
lib = errset(ddGetObj(LIB))
printf("S3CMK-PATH %L\n" errset(lib->path))
printf("S3CMK-TECH %L\n" errset(lib->techName))
printf("S3CMK-CELLS %L\n" car(errset(length(dbGet(lib "cells")))))
printf("MKLIB_DONE\n")
exit()
