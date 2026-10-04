;; Qoder -> RHEL6 -> IC617 SKILL smoke test
;; Pure SKILL only: no libManager.init, no dbOpenCellViewByType, no PDK/cds.lib,
;; no write of any design data. It must be safe to run against a real project dir.
;; The OK token is printed before anything that could fail, so a missing token
;; means the interpreter never got here.

printf("QODER_IC617_SKILL_SMOKE_TEST_BEGIN\n")
printf("QODER_IC617_SKILL_SMOKE_TEST_OK\n")
