;; sc1_s3c3_gui_open.il -- run by scripts/s3c3_gui_shot.sh inside the one GUI session this round.
;;
;; Section 6's requirement: open the real views with the documented keyword form and let the window
;; manager map them; the capture is done from the shell, never synchronously from here, and this file
;; never exits the session -- the launcher keeps it alive, reads the windows, then terminates the
;; session it started. Every view opens with ?mode "r", so nothing can be written from a window.

goTargets = list(
  list("sc1_scan_power_1ch_s3c" "schematic")
  list("sc1_scan_power_1ch_s3c" "symbol")
  list("c2mos_dff" "schematic")
  list("sc1_s3b_p33_bank_7" "schematic")
  list("sc1_ls_c1_top_r2d" "schematic")
  list("sc1_r3_scan_chain_1ch" "schematic")
)

procedure(goVal(v) if(v v "NONE"))

printf("GW-BEGIN\n")
foreach(t goTargets
  w = car(errset(geOpen(?lib "microled_scan_s3c" ?cell nth(0 t) ?view nth(1 t) ?mode "r")))
  printf("GW-OPEN %L %L window=%L winId=%L\n" nth(0 t) nth(1 t) goVal(w)
         goVal(car(errset(dbGet(w 'windowId)))))
)
printf("GW-WINDOWS\n")
wl = car(errset(hiGetWindowList()))
foreach(w wl
  printf("GW-WIN type=%L cell=%L view=%L name=%L winId=%L\n" goVal(w~>type)
         goVal(if(w~>cellView w~>cellView~>cellName nil))
         goVal(if(w~>cellView w~>cellView~>viewName nil)) goVal(w~>name)
         goVal(car(errset(dbGet(w 'windowId)))))
)
printf("GW-END-OF-OPENS\n")
nil
