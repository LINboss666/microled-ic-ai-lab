; SCAN_UNIT_TEAM_BEAUTIFY: read-only geometry dump of the sheets about to be arranged.
;
; Written fresh instead of reusing sc1_s1_s3c1_geom_dump.il because that one carries the source
; machine's cell list and output paths. This round needs one thing: where every instance, pin, wire
; and label of these sheets actually is, so the arrangement is computed from THIS library rather
; than replayed from somebody's coordinates.
;
; Mechanics learned the hard way in this build, all applied below:
;   * one errset per value. car(errset(errset(x))) nests the value a level deeper and silently turns
;     every length() into 1, which is how the first two attempts here reported 8 instances as 1.
;   * the -> accessor form works; ~ is a parse error here.
;   * every printf is on a single line, because an unbalanced parenthesis in SKILL swallows the rest
;     of the file and an aborted load still exits 0.
;   * cv->terms is empty on this build; cv->terminals is the one that carries the ports.
;
; Run: S3CB_CELLS="sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_scan_power_1ch_s3c" \
;      bash scripts/sc1_s3c_run_oa.sh <this file under s3c_oa/skill> 600 S3BG_DONE
printf("S3BG-BEGIN\n")
LIBN = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIBN LIBN "sc1_s3c_team_pretty")
CEN = car(errset(getShellEnvVar("S3CB_CELLS")))
CSTR = if(CEN CEN "sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_scan_power_1ch_s3c")
CELLS = car(errset(parseString(CSTR " ")))
printf("S3BG-LIB %L CELLS %L\n" LIB CELLS)

procedure(gg(obj key)
  car(errset(dbGet(obj key)))
)
procedure(gtext(obj)
  if(gg(obj "text") gg(obj "text") gg(obj "name"))
)
procedure(gown(obj)
  if(gg(obj "owner") gg(gg(obj "owner") "name") "NIL")
)

foreach(CELL CELLS
  cv = dbOpenCellViewByType(LIB CELL "schematic" "schematic" "r")
  when(cv
    printf("S3BG-CELL %L insts=%L nets=%L shapes=%L terms=%L\n" CELL length(gg(cv "instances")) length(gg(cv "nets")) length(gg(cv "shapes")) length(car(errset(cv->terminals))))
    foreach(inst gg(cv "instances")
      printf("S3BG-INST cell=%L name=%L master=%L/%L bbox=%L type=%L\n" CELL gg(inst "name") gg(gg(inst "master") "libName") gg(gg(inst "master") "cellName") gg(inst "bBox") gg(inst "objType"))
      foreach(it gg(inst "instTerms")
        printf("S3BG-ITERM cell=%L inst=%L term=%L dir=%L net=%L\n" CELL gg(inst "name") gg(it "name") gg(it "direction") gg(gg(it "net") "name"))
      )
    )
    foreach(fig gg(cv "shapes")
      printf("S3BG-FIG cell=%L type=%L bbox=%L owner=%L text=%L net=%L layer=%L\n" CELL gg(fig "objType") gg(fig "bBox") gown(fig) gtext(fig) gg(gg(fig "net") "name") gg(gg(fig "layer") "name"))
    )
    foreach(net gg(cv "nets")
      printf("S3BG-NET cell=%L name=%L pins=%L\n" CELL gg(net "name") length(gg(net "pins")))
      foreach(pin gg(net "pins")
        printf("S3BG-PIN cell=%L net=%L objType=%L owner=%L bbox=%L\n" CELL gg(net "name") gg(pin "objType") gown(pin) gg(pin "bBox"))
      )
    )
    foreach(tm car(errset(cv->terminals))
      printf("S3BG-TERM cell=%L name=%L dir=%L net=%L\n" CELL gg(tm "name") gg(tm "direction") gg(gg(tm "net") "name"))
    )
    dbClose(cv)
  )
  unless(cv printf("S3BG-OPEN-FAILED %L\n" CELL))
  sy = dbOpenCellViewByType(LIB CELL "symbol" nil "r")
  when(sy
    printf("S3BG-SYM cell=%L figs=%L terms=%L bbox=%L\n" CELL length(gg(sy "figures")) length(car(errset(sy->terminals))) gg(sy "bBox"))
    foreach(fig gg(sy "figures")
      printf("S3BG-SYMF cell=%L type=%L bbox=%L text=%L owner=%L layer=%L\n" CELL gg(fig "objType") gg(fig "bBox") gtext(fig) gown(fig) gg(gg(fig "layer") "name"))
    )
    foreach(tm car(errset(sy->terminals))
      printf("S3BG-SYMT cell=%L name=%L dir=%L pins=%L\n" CELL gg(tm "name") gg(tm "direction") length(gg(tm "pins")))
      foreach(pin gg(tm "pins")
        printf("S3BG-SYMPIN cell=%L term=%L type=%L bbox=%L owner=%L\n" CELL gg(tm "name") gg(pin "objType") gg(pin "bBox") gown(pin))
        foreach(fig car(errset(dbGet(pin "figs")))
          printf("S3BG-PINFIG cell=%L term=%L figType=%L bbox=%L\n" CELL gg(tm "name") gg(fig "objType") gg(fig "bBox"))
          foreach(ch car(errset(dbGet(fig "children")))
            printf("S3BG-PINCHILD cell=%L term=%L type=%L text=%L xy=%L\n" CELL gg(tm "name") gg(ch "objType") gtext(ch) gg(ch "xy"))
          )
        )
      )
    )
    dbClose(sy)
  )
  unless(sy printf("S3BG-SYM-MISSING %L\n" CELL))
)
printf("S3BG_DONE\n")
exit()
