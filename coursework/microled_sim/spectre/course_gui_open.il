;; R2 course GUI open: defer window creation to the event loop, then open the
;; saved course schematic read-only. Loaded by the isolated $HOME/.cdsinit that
;; the launcher writes; this file must NOT call exit() (the window has to stay).
printf("CG-BEGIN\n")
when(getd('hiEnqueueCmd)
  hiEnqueueCmd("geOpen(?lib \"course_sim_20261112\" ?cell \"course_sink_unit\" ?view \"schematic\" ?mode \"r\")")
  hiEnqueueCmd("printf(\"GW-READY-FOR-MANUAL-CAPTURE\\n\")")
)
when(getd('hiEnqueueCmd) == nil
  geOpen(?lib "course_sim_20261112" ?cell "course_sink_unit" ?view "schematic" ?mode "r")
  printf("GW-READY-FOR-MANUAL-CAPTURE\n")
)
printf("CG-ENQUEUED\n")
nil
