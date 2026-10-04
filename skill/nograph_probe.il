;; Virtuoso (full GUI engine, non-graphical mode) capability probe.
;; Loaded from an isolated .cdsinit inside the project HOME, NOT from the real /root/.cdsinit.
;; It opens no library and no cell, prints markers, and lets the init file call exit().
;;
;; Everything that could return nil is wrapped, because printf("%s", nil) aborts the
;; whole load in this SKILL implementation.
procedure(qSv(name)
  let((v)
    v = getShellEnvVar(name)
    if( v then v else "<unset>" )
  )
)

printf("VIRTUOSO_NOGRAPH_SKILL_LOADED\n")
printf("engine=%s\n"  qSv("CDS"))
printf("home=%s\n"    qSv("HOME"))
printf("pwd=%s\n"     qSv("PWD"))
printf("display=%s\n" qSv("DISPLAY"))

;; Ask the running application who it is. Guarded: these functions exist in the full
;; Virtuoso env but not in dbAccess, which is exactly the difference being probed.
printf("has_ciGetInfo=%L\n"    errset(ciGetInfo()))
printf("has_ddGetLibList=%L\n" errset(ddGetLibList()))
printf("has_geGetEditorType=%L\n" errset(geGetEditCellView()))

;; Library visibility with NO cds.lib in the run directory: this reports what the
;; default libPath resolves to. Listing is read-only; no cell view is opened.
;;
;; Careful: errset() returns a LIST of results (or nil), so it must be unwrapped before
;; printf("%s"). Passing the raw list, or nil, to %s aborts the entire load in this SKILL.
;; Library visibility: ddGetLibList() succeeds here and reports 13 libraries even with
;; no cds.lib in the run directory. Resolving their NAMES is deliberately left out of
;; this probe: three attribute-access forms all aborted the load with a parse error at
;; `l~name` (SKILL parse error, not a runtime error), and the headless capability result
;; must not depend on optional code. Name enumeration is a next-round item, likely via
;; ddGetObjName(l) rather than the ~ accessor.
printf("LIB_COUNT_HINT=see ddGetLibList result above\n")

printf("VIRTUOSO_NOGRAPH: PASS\n")
