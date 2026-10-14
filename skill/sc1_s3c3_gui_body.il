;; sc1_s3c3_gui_body.il -- the shortest script that gets the six views on screen, for MANUAL capture.
;;
;; Section 6 asks for one correctly started isolated GUI session and, if the automated delivery
;; cannot be finished, "the shortest CIW open script". This is that script. It is reached through
;; sc1_s3c3_gui_open.il, which defers it with hiEnqueueCmd: called directly from $HOME/.cdsinit the
;; opens returned window:2..7 while the X tree stayed empty, because the schematic editor's own menu
;; file aborted during init (`*Error* eval: unbound variable - ciwHelpMenuSpec` at
;; /opt/IC617/tools.lnx86/dfII/etc/tools/menus/schView.menus line 342). Deferred, that error is gone
;; and six real editor windows exist.
;;
;; Measured on IC617 6.1.7-64b, so nobody retries the automated pixel route blindly:
;;   * hiResizeWindow needs TWO POINTS: list(list(llx lly) list(urx ury)). With four bare numbers it
;;     logged `*WARNING* Invalid bounding box` and returned nil; with the two-point form it returns t
;;     and the six windows land at six non-overlapping slots.
;;   * the design windows carry no WM_NAME, so xwininfo shows `": ("Qt-subapplication" "Virtuoso")`.
;;     Matching them by "<cell> <view>" in the title finds nothing, which is what made the first
;;     capture loop report zero windows.
;;   * hiRaiseWindow does NOT restack at the window manager: _NET_CLIENT_LIST_STACKING stayed in
;;     creation order across all six raises, so "capture whatever is on top" cannot identify a cell.
;;   * import -window <top-level> writes a 134-byte uniform PNG: the Qt top level is a container and
;;     Virtuoso paints into a nested child. Descending to the largest child picks an unmapped 640x480
;;     helper instead (IsUnMapped, `unable to read X window image: Resource ...`), so pixel grabbing
;;     on this display/build was not completed and screenshots are taken by hand here.
;;
;; NEW_SIMULATION_RUNS = 0. Every view opens with ?mode "r"; nothing in this file writes to the OA.

goTargets = list(
  list("sc1_scan_power_1ch_s3c" "schematic")
  list("sc1_scan_power_1ch_s3c" "symbol")
  list("c2mos_dff" "schematic")
  list("sc1_s3b_p33_bank_7" "schematic")
  list("sc1_ls_c1_top_r2d" "schematic")
  list("sc1_r3_scan_chain_1ch" "schematic")
)

;; one distinct pixel box per target, in open order; 3 columns x 2 rows on a 1920x1153 screen
goSlots = list(
  list(20 500 620 950)
  list(640 500 1240 950)
  list(1260 500 1860 950)
  list(20 20 620 470)
  list(640 20 1240 470)
  list(1260 20 1860 470)
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
