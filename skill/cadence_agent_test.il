;; Bonus round-trip: Windows -> SSH -> RHEL6 -> IC617 SKILL, one command.
;; Prints time, cwd and a custom marker. Still pure SKILL: no library, no PDK,
;; no cell view, no writes.
;;
;; qSv() exists because getShellEnvVar returns nil for an unset variable and
;; printf("%s", nil) aborts the whole load with "format spec incompatible with data".
;;
;; QODER_RUN_TS / QODER_HOST are injected by run_skill.sh: this dbAccess build has no
;; clock built-in, and bash does not export HOSTNAME in a non-login shell.
procedure( qSv(name)
  let((v)
    v = getShellEnvVar(name)
    if( v then v else "<unset>" )
  )
)

printf("CADENCE_AGENT_TEST_BEGIN\n")
printf("time_utc=%s\n"  qSv("QODER_RUN_TS"))
printf("cwd=%s\n"       qSv("PWD"))
printf("user=%s\n"      qSv("USER"))
printf("host=%s\n"      qSv("QODER_HOST"))
printf("cds_root=%s\n"  qSv("CDS"))
printf("marker=%s\n"    "QODER-IC617-BRIDGE-LIVE")
printf("CADENCE_AGENT_TEST_OK\n")
