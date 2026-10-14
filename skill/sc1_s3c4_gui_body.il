;; sc1_s3c4_gui_body.il -- the four AFTER views the S3C4 review needs, opened read-only for hand
;; screenshots, one per grid slot so nothing covers anything else.
;;
;; Reachable only through sc1_s3c4_gui_open.il (hiEnqueueCmd). The view list is exactly the four the
;; task book names: top Symbol, top schematic, chain schematic, level-shifter parent schematic. The DFF
;; and bank images were unaffected by this round and are reused from the human set, so they are not
;; opened here. Every window opens ?mode "r" -- nothing in this file can write to the OA -- and
;; NEW_SIMULATION_RUNS = 0.
;;
;; Two measured call shapes are relied on and are easy to get wrong: hiResizeWindow needs
;; list(list(llx lly) list(urx ury)) (four bare numbers log `Invalid bounding box` and return nil),
;; and design windows carry no WM_NAME, so a person identifies them by clicking the title bar of each
;; slot, not by a title match in a script.

goTargets = list(
  list("sc1_scan_power_1ch_s3c" "schematic")
  list("sc1_scan_power_1ch_s3c" "symbol")
  list("sc1_r3_scan_chain_1ch" "schematic")
  list("sc1_ls_c1_top_r2d" "schematic")
)

;; 2 columns x 2 rows of 600x450 on the 1920x1153 desktop, in open order
goSlots = list(
  list(20 500 620 950)
  list(640 500 1240 950)
  list(20 20 620 470)
  list(640 20 1240 470)
)

procedure(goVal(v) if(v v "NONE"))

printf("GW-BEGIN\n")
goWins = nil
goN = 0
foreach(tgt goTargets
  w = car(errset(geOpen(?lib "microled_scan_s3c" ?cell nth(0 tgt) ?view nth(1 tgt) ?mode "r")))
  box = nth(goN goSlots)
  rs = car(errset(hiResizeWindow(w list(list(nth(0 box) nth(1 box)) list(nth(2 box) nth(3 box))))))
  errset(hiRaiseWindow(w))
  errset(hiRedraw(w))
  printf("GW-OPEN n=%L %L %L window=%L resize=%L\n"
         goN nth(0 tgt) nth(1 tgt) goVal(w) goVal(rs))
  goWins = cons(w goWins)
  goN = goN + 1
)
goWins = reverse(goWins)
printf("GW-WINDOWS count=%L\n" length(goWins))
goI = 0
foreach(w goWins
  printf("GW-WIN n=%L cell=%L view=%L\n" goI goVal(if(w w~>cellView~>cellName nil))
         goVal(if(w w~>cellView~>viewName nil)))
  goI = goI + 1
)
printf("GW-READY-FOR-MANUAL-CAPTURE opens=%L\n" goI)
nil
