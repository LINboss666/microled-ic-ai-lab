printf("RP-BEGIN\n")
foreach(f list('schCheck 'schCreate 'schCreateWire 'schCreatePin 'hiCheckAndSave 'asiNetlist 'asiRawNetlist
               'hiSetInitFunc 'dbCheck 'dbCreateInstTermByPosition 'dbCreatePin 'dbCreateNet 'dbSave 'geGetEditCellView)
  printf("RP %L => %L\n" f getd(f))
)
printf("RP_DONE\n")
exit()
