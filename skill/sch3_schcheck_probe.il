; SCH-3 follow-up probe: is the Schematic Editor package really unavailable in batch, or was the
; availability test itself wrong?
;
; Why this matters: since SCH-1 this project has carried the statement "schCheck is undefined in a
; batch session", because getd('schCheck) returned nil and an early load() of schematic.cxt failed.
; The dbCheck run before this one called schCheck by literal name inside errset and it executed and
; printed two solder-dot warnings and returned (0 2). So the tool is reachable; what is not reachable
; is *querying* for it. Every earlier conclusion built on "schCheck does not exist" has to be
; re-stated on that basis, and a reviewer deserves the measurement rather than the belief.
;
; Read-only: every cellview here is opened with mode "r"; nothing is saved; the C2MOS cells are only
; inspected so their warning count can be compared with what the user saw in the GUI.
;
; Run: MODE=nograph bash scripts/sch_virtuoso.sh /root/microled_ai_project/skill/sch3_schcheck_probe.il 600 SC_DONE
printf("SC-BEGIN\n")
printf("SC-GETD schCheck=%L schCreate=%L schCreateWire=%L schCheckAndSave=%L hiCheckAndSave=%L\n"
       getd('schCheck) getd('schCreate) getd('schCreateWire) getd('schCheckAndSave)
       getd('hiCheckAndSave))

; the literal call is the only dispatch that works on this build (AGENTS item 8: dynamic dispatch
; through funcall/a symbol is nil here, and getd evidently does not see editor-package functions)
printf("SC-CALL-LITERAL schCheck => %L\n" errset(schCheck))
printf("SC-CALL-LITERAL schCreate => %L\n" errset(schCreate))

procedure(scCheckCell(lib cell view)
  let((cv res)
    cv = car(errset(dbOpenCellViewByType(lib cell view "schematic" "r")))
    unless(cv == nil
      printf("SC-OPEN %L/%L %L instances=%L\n" lib cell view length(dbGet(cv "instances")))
      res = errset(schCheck(cv))
      printf("SC-SCHCHECK %L/%L raw=%L\n" lib cell res)
      printf("SC-SCHCHECK %L/%L car=%L cadr=%L\n" lib cell car(res) car(cdr(res)))
      dbClose(cv)
    )
    when(cv == nil printf("SC-OPEN-FAILED %L/%L\n" lib cell))
  )
)

foreach(cell list("data_sink_1ch" "data_bias_ref" "data_pdk_param_smoke"
                  "c2mos_dff_1bit_paramfix" "c2mos_dff_1bit")
  scCheckCell("microled_cells" cell "schematic")
)
printf("SC_DONE\n")
exit()
