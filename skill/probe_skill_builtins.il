;; Capability probe: which SKILL built-ins does this IC617 build actually provide?
;; Read-only; used to pick safe primitives for the bonus script.
printf("PROBE_BEGIN\n")

foreach(c '(getcwd gettime daydate date time gethostname getpid getusername getshellvar getShellEnvVar getenv pwd)
  printf("call(%-16s) -> %L\n" c errset(funcall(c)))
)

printf("getShellEnvVar(PWD) -> %L\n" errset(getShellEnvVar("PWD")))
printf("getShellEnvVar(HOME) -> %L\n" errset(getShellEnvVar("HOME")))
printf("skill shell name -> %L\n" errset(getshellname()))
printf("PROBE_END\n")
