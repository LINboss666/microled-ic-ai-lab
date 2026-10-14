;; sc1_s3c2_rename_probe.il
;;
;; Can a net's name be set in batch? The loop test proved the connection survives the re-lay
;; (Xchain.gate33 and Xbank.bgate sit on ONE net, every other net kept its name) but the internal
;; net lost its name to an auto one (net11) when the figure set was replaced, and section 5 asks for
;; the same-view real net naming. This file tries the attribute assignment on this round's scratch
;; cellview, saves, reopens from disk and reads the name back -- before it is used anywhere real.
;; Writes only to microled_scan_s3c's scratch cellview. NEW_SIMULATION_RUNS = 0.

rpLib = "microled_scan_s3c"
rpCell = "s3c2_loop_top"
rpFrom = "net11"
rpTo = "gate33"

procedure(rpVal(v)
  if(v == nil "NONE" v)
)

procedure(rpSetName(o nm)
  o~>name = nm
)

procedure(rpFind(cv nm)
  let((out)
    out = nil
    foreach(n cv~>nets
      when(out == nil
        when(equal(rpVal(n~>name) nm) out = n)
      )
    )
    out
  )
)

procedure(rpReport(tag cv)
  let((k)
    k = 0
    foreach(n cv~>nets
      k = k + 1
      printf("RP-%L %L net=%L\n" tag k rpVal(n~>name))
    )
  )
)

printf("RP-BEGIN\n")
cv = car(errset(dbOpenCellViewByType(rpLib rpCell "schematic" "schematic" "a")))
printf("RP-OPEN %L nets=%L\n" cv != nil length(cv~>nets))
when(cv != nil
  old = rpFind(cv rpFrom)
  printf("RP-FIND %L %L\n" rpFrom old != nil)
  when(old != nil
    r = car(errset(rpSetName(old rpTo)))
    printf("RP-SET rc=%L err=%L now=%L\n" r != nil r rpVal(if(old~>net old~>name old~>name)))
    printf("RP-AFTER-SET %L\n" rpVal(if(rpFind(cv rpTo) != nil rpTo "MISSING")))
    printf("RP-SAVE %L\n" car(errset(dbSave(cv))) != nil)
    dbClose(cv)
  )
  when(old == nil
    dbClose(cv)
  )
)
again = car(errset(dbOpenCellViewByType(rpLib rpCell "schematic" "schematic" "r")))
printf("RP-REOPEN %L\n" again != nil)
when(again != nil
  rpReport("REOPEN" again)
  dbClose(again)
)
printf("RP-DONE\n")
nil
