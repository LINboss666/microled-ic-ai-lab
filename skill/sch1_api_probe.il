;; SCH-1 step 5: which building blocks this session really has. getd answers "defined or
;; not"; calling a function inside errset cannot, because an undefined name and a function
;; that returns nil both look like nil. Read-only.

printf("SCHK5_BEGIN\n")

foreach(fn list('schCreate, 'schCreateWire, 'schCreatePin, 'schCreateRect, 'schCreateLabel,
                'schCheck, 'schDelete, 'schOpenWindow, 'vi, 'hiSetInitFunc, 'hiGetWindowList,
                'hiCheckAndSave, 'dbCreateNet, 'dbCreateWire, 'dbCreateRect, 'dbCreateShape,
                'dbCreateLabel, 'dbCreateInst, 'dbCreateParamInst,
                'dbCreateParamInstByMasterName, 'dbCreateTerm, 'dbCreatePort,
                'dbCreateCellView, 'ddCreateCellView, 'dbCreateLib, 'ddCreateLib,
                'hiCreateDirLib, 'dbSave, 'dbCreateInstTerm, 'dbSetFigNet, 'dbCreateBranch,
                'hiCreateAppObjView, 'hiOpenCellView, 'leCreateIntHierchy, 'techGetTechFile,
                'dbGetCellPrimaryView, 'ddGetCellPrimaryView, 'ddGetObjCellNames,
                'ddGetObjName, 'ddGetObjPath, 'ddGetObjViewNames, 'ddGetObjTechnoName)
  printf("F %-34s %L\n" fn errset(getd(fn) != nil))
)

lib = errset(ddGetObj("smic18mmrf"))
printf("SMIC_OBJ %L\n" lib)
printf("SMIC_ddGetObjName %L\n" errset(ddGetObjName(lib)))
printf("SMIC_ddGetObjPath %L\n" errset(ddGetObjPath(lib)))
printf("SMIC_ddGetObjCellNames %L\n" errset(ddGetObjCellNames(lib)))
printf("SMIC_ddGetObjTechnoName %L\n" errset(ddGetObjTechnoName(lib)))
n18 = errset(ddGetObj("smic18mmrf", "n18"))
printf("N18_OBJ %L\n" n18)
printf("N18_ddGetObjName %L\n" errset(ddGetObjName(n18)))
printf("N18_views %L\n" errset(ddGetObjViewNames(n18)))
printf("N18_primary %L\n" errset(ddGetCellPrimaryView(n18)))
printf("N18_propTable %L\n" errset(ddGetObjPropTable(n18)))

printf("SCHK5_END\n")
