;; SCH-1 B/C step 2: does this build let us (a) create our own library, (b) attach the
;; teacher technology, (c) instantiate the PCell device master n18/p18 into a schematic, and
;; (d) read the effective W/L back? Every probe call is errset-wrapped, so a missing or
;; differently-shaped function shows up as an "undefined function"/usage line in the log
;; instead of aborting the run.
;;
;; Side effects are confined to libraries/cells this script creates inside
;; /root/microled_ai_project/cadence_work (never the PDK, never an existing library):
;; it refuses to touch a library or cell that already exists and says so.

printf("SCHMK_BEGIN\n")

printf("CWD %L\n" errset(getShellEnvVar("PWD")))

;; --- is the design library already there? never overwrite ---
already = errset(ddGetObj("microled_cells"))
printf("LIB_ALREADY_THERE %L\n" already)

when(already == nil
  printf("MKLIB_TRY %L\n" errset(hiCreateDirLib("microled_cells")))
)
lib = errset(ddGetObj("microled_cells"))
printf("LIB_NOW %L\n" lib)
printf("LIB_PATH_VIA_GETOBJ %L\n" errset(ddGetObjName(lib)))
printf("LIB_PATH %L\n" errset(lib->path))

;; --- what technology does the foundry library carry, and can we name it? ---
printf("TECH_OF_SMIC %L\n" errset(dbGetTechnologyName(errset(ddGetObj("smic18mmrf")))))
printf("TECH_LIST %L\n" errset(hiGetTechnologyList()))
printf("TECH_NAMES %L\n" errset(dbGetTechNames("smic18mmrf")))
printf("ATTACHED_TECH %L\n" errset(lib->techName))

;; --- does a scratch cell exist? refuse if so ---
probeCell = "sch1_probe"
ce = errset(ddGetObj("microled_cells" probeCell))
printf("PROBE_CELL_ALREADY %L\n" ce)

when(lib
  when(ce == nil
    cv = errset(schCreate("microled_cells" probeCell "schematic" "schematic"))
    printf("SCHCREATE %L\n" cv)
    when(cv
      printf("SCHCREATE_TYPE %L\n" errset(cv->viewType))

      ;; PCell-style instantiation is the only legitimate way in: the device master has no
      ;; schematic view of its own (measured), it is a parameterised foundry cell.
      i1 = errset(dbCreateParamInstByMasterName(cv "smic18mmrf" "n18" "schematic"
                                               list(100:100)
                                               :paramList list(list("w" "2e-6")
                                                               list("l" "2e-7"))
                                               :role "master"))
      printf("INST_PARAMINST_n18 %L\n" i1)

      i2 = errset(dbCreateInst(cv "smic18mmrf" "n18" "schematic" list(300:300)))
      printf("INST_DBCREATE_n18 %L\n" i2)

      i3 = errset(dbCreateInst(cv "smic18mmrf" "n18" "symbol" list(500:300)))
      printf("INST_DBCREATE_SYMVIEW_n18 %L\n" i3)

      printf("INST_LIST %L\n" errset(setof(f dbGetFigures(cv "instance") f->objType)))
      printf("SAVE %L\n" errset(ovSaveView(cv)))
      errset(ovClose(cv))
    )
  )
)

;; --- what functions exist at all? (getd cannot answer: these are autoloaded per context) ---
foreach(fn list('schCreate, 'schCreateWire, 'schCreatePin, 'dbCreateParamInst,
                'dbCreateParamInstByMasterName, 'hiCreateDirLib, 'schCheck,
                'schDelete, 'hiCheckAndSave, 'dbGetTechnologyName, 'siCreateInstance)
  printf("CALL_EXISTS %s %L\n" fn errset(funcall(fn)))
)

printf("SCHMK_END\n")
