;; Capability probe #2: direct calls (funcall-by-symbol returned nil for everything,
;; so each candidate is called literally and guarded with errset).
printf("PROBE2_BEGIN\n")
printf("today()            -> %L\n" errset(today()))
printf("now()              -> %L\n" errset(now()))
printf("date()             -> %L\n" errset(date()))
printf("getenv(PATH)       -> %L\n" errset(getenv("PATH")))
printf("getShellEnvVar(USER)      -> %L\n" errset(getShellEnvVar("USER")))
printf("getShellEnvVar(HOSTNAME)  -> %L\n" errset(getShellEnvVar("HOSTNAME")))
printf("getShellEnvVar(CDS)       -> %L\n" errset(getShellEnvVar("CDS")))
printf("getBuildInformation       -> %L\n" errset(getBuildInformation('virtuoso)))
printf("skillVersionName   -> %L\n" errset(skillVersionName()))
printf("PROBE2_END\n")
