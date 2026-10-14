;; sc1_s3c4_gui_open.il -- S3C4 AFTER views: queue the opens after init instead of doing them here.
;;
;; Same shape the S3C3 measurements proved correct: opening from $HOME/.cdsinit directly hits the
;; vendor menu abort (`*Error* eval: unbound variable - ciwHelpMenuSpec`, schView.menus line 342) and
;; geOpen then returns window objects with no X window behind them. hiEnqueueCmd defers the work until
;; the CIW and the editor menus exist. This file does not open windows and does not exit.

printf("GW-ENQUEUE-BEGIN\n")
goPath = "/root/microled_ai_project/cadence_work/s3c_oa"
printf("GW-ENQUEUE hiEnqueueCmd=%L\n" if(getd('hiEnqueueCmd) "EXISTS" "NIL"))
when(getd('hiEnqueueCmd)
  hiEnqueueCmd(sprintf(nil "load(\"%s/sc1_s3c4_gui_body.il\")" goPath))
)
when(getd('hiEnqueueCmd) == nil
  load(sprintf(nil "%s/sc1_s3c4_gui_body.il" goPath))
)
printf("GW-ENQUEUE-DONE\n")
nil
