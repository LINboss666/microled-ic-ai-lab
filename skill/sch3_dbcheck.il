; SCH-3 section 12 and 6: the honest state of "check and save", and of pin directions.
;
; Two things are recorded here because both are limits of this batch build, not results to be spun:
;   * schCheck belongs to the Schematic Editor package, which is not registered for a batch session
;     (measured repeatedly since SCH-1: schCreate/schCheck/schCreateWire undefined). dbCheck IS
;     available and is run, but dbCheck checks the OA object graph -- connectivity, types, required
;     properties -- and is not the editor's electrical/consistency check. It is reported as dbCheck,
;     never as "SCHEMATIC_CHECK_AND_SAVE: PASS".
;   * the ports that spiceIn/ASG created are basic/iopin instances; the schematic's term list is
;     empty in a batch session, so a pin DIRECTION cannot be read back here. The directions declared
;     in the import netlist (SCH-3 section 6) are recorded in the netlist file, which is the artifact
;     the reviewer can check; the OA-side direction needs the GUI.
;
; Run: SCH3_CELLS="data_sink_1ch data_bias_ref" MODE=nograph bash scripts/sch_virtuoso.sh \
;        /root/microled_ai_project/skill/sch3_dbcheck.il 600 DC3_DONE
printf("DC3-BEGIN\n")
LIB = "microled_cells"
CELLS_ENV = getShellEnvVar("SCH3_CELLS")
CELLS_STR = if(CELLS_ENV CELLS_ENV "data_sink_1ch data_bias_ref")
CELLS = car(errset(parseString(CELLS_STR " ")))

printf("DC3-API schCheck=%L schCreate=%L schCreateWire=%L dbCheck=%L dbSave=%L hiCheckAndSave=%L\n"
       getd('schCheck) getd('schCreate) getd('schCreateWire) getd('dbCheck) getd('dbSave)
       getd('hiCheckAndSave))

foreach(CELL CELLS
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "a")
  when(cv
    printf("DC3-OPEN %L/%L instances=%L nets=%L terms=%L\n" LIB CELL
           length(dbGet(cv "instances")) length(dbGet(cv "nets")) length(cv->terms))
    printf("DC3-DBCHECK %L => %L\n" CELL errset(dbCheck(cv)))
    printf("DC3-SCHCHECK %L => %L\n" CELL errset(schCheck(cv)))
    foreach(inst dbGet(cv "instances")
      printf("DC3-INST %L %L master=%L/%L dirProp=%L dirArrow=%L\n" CELL inst->name
             dbGet(dbGet(inst "master") "libName") dbGet(dbGet(inst "master") "cellName")
             car(errset(dbGet(inst "direction"))) car(errset(inst->direction)))
    )
    printf("DC3-SAVE %L => %L\n" CELL errset(dbSave(cv)))
    dbClose(cv)
  )
  unless(cv printf("DC3-OPEN-FAILED %L\n" CELL))
)
printf("DC3_DONE\n")
exit()
