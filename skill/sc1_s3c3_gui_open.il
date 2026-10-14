;; sc1_s3c3_gui_open.il -- loaded by $HOME/.cdsinit; defers the window work to the event loop.
;;
;; Section 6 asks for exactly this shape: the init script does not open windows itself and does not
;; exit, it queues the opens so the design windows are created after the menus and the CIW exist.
;; If hiEnqueueCmd is somehow absent, fall back to running the body inline.

;; direct call measured this way: geOpen returned window:2..7 and hiRaiseWindow/hiRedraw answered t,
;; yet the X tree stayed empty and the log carried `*Error* eval: unbound variable - ciwHelpMenuSpec`
;; out of /opt/IC617/tools.lnx86/dfII/etc/tools/menus/schView.menus line 342 -- the schematic editor's
;; own menu failing to load during init. Vendor files are out of bounds, so deferral is the fix.

printf("GW-ENQUEUE-BEGIN\n")
goPath = "/root/microled_ai_project/cadence_work/s3c_oa"
printf("GW-ENQUEUE hiEnqueueCmd=%L\n" if(getd('hiEnqueueCmd) "EXISTS" "NIL"))
when(getd('hiEnqueueCmd)
  hiEnqueueCmd(sprintf(nil "load(\"%s/sc1_s3c3_gui_body.il\")" goPath))
)
when(getd('hiEnqueueCmd) == nil
  load(sprintf(nil "%s/sc1_s3c3_gui_body.il" goPath))
)
printf("GW-ENQUEUE-DONE\n")
nil
