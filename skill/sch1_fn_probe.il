printf("FP-BEGIN\n")
foreach(f list('dbCreateNet 'dbCreateNetToTerm 'dbCreateInstTerm 'dbAssignNetToInstTerm 'dbCreateWire
               'dbCreateShape 'dbCreateRect 'dbCreatePath 'dbCreateLabel 'dbCreateFigTerm 'dbCreateNetLabel
               'dbCreatePin 'dbCreateTerm 'dbCheck 'dbVerifyConnectivity 'dbConnectNetToTerm 'dbGetNets
               'dbCreateInst 'dbCreateParamInst 'dbCreateParamInstByMasterName 'dbSave 'dbSetElementVisible
               'dbCreateNetToTerm 'dbMergeNets 'dbSetPropValue 'dbGetProp 'dbCreateProp 'dbDeleteNet
               'dbCreateShape 'dbCreateFig 'dbCreateFigure 'dbCreateSchematicFig 'dbCreateWireFigure)
  printf("FP %L => %L\n" f getd(f))
)
printf("FP_DONE\n")
exit()
