; SCAN-1 S3-C1 section 4: which editor-side operations exist in THIS session once the schematic
; package has been pulled in -- because the answer decides how the symbol pin groups and the
; schematic regions may be repositioned without breaking a single net.
;
; Measured so far in batch: dbCreateRect/dbCreateLine/dbCreateLabel/dbMoveFig/dbCopyFig are lambdas
; from the start, while schCheck and schCreateWire appear only AFTER the package arrives late
; (sc1_s3c1_apply_dirs.il ran schCheck on all 16 views and printed (errors warnings) per schematic).
; What is still unknown, and what must not be guessed:
;   * can a figure be destroyed? The batch build has no dbDeleteObj, so re-routing a parent
;     schematic after its child's symbol pins move needs another way to remove the old wire.
;   * is there a graphics window at all in this session, and can the view be exported as an image
;     (that is what the reviewer asked to see: 顶层 schematic、顶层 symbol、DFF 分区、bank)?
;   * do the editor's own placement helpers exist (they are the ones that stretch attached wires)?
;
; Read-only: nothing is created, moved or saved here. Only getd lookups, plus the load trigger.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_edit_probe.il 600 S3C1X_DONE
printf("S3C1X-BEGIN\n")
LIB = "microled_scan_s3c"

procedure(s3c1xGetd(stage names)
  let((fn)
    foreach(fn names printf("S3C1X-API %L %L=%L\n" stage fn getd(fn)))
  )
)

s3c1xGetd("STARTUP" list('dbDeleteObj 'dbDeleteInst 'geDeleteSel 'schDelete 'geDelete 'schDeleteFig
                         'dbDestroy 'hiDeleteWindow 'schCreateWire 'dbCreateWire 'schWire
                         'hiCreateWindow 'hiGetWindow 'hiGetEditWin 'hiGetSession
                         'hiPrint 'hiPrintBitmap 'hiSaveSnapshot 'hiGetGraphicWinExtent
                         'geCreateRect 'geCreateRectangles 'schMoveInst 'geMoveFig 'schSaveView
                         'schOpen 'hiCheckAndSave 'schCheck 'dbSetWindowDisplay 'hiRedraw
                         'dbSaveEntity 'hiEditWin))

cv = car(errset(dbOpenCellViewByType(LIB "sc1_s3b_p33_bank_7" "schematic" "schematic" "r")))
printf("S3C1X-OPENED %L terms=%L\n" cv car(errset(length(cv->terminals))))
when(cv
  printf("S3C1X-DBCHECK %L\n" errset(dbCheck(cv)))
  printf("S3C1X-TRIGGER %L\n" errset(dbCreateRect(cv list(list(0.0 0.0) list(0.1 0.1)))))
  printf("S3C1X-SCHCHECK %L\n" errset(schCheck(cv)))
  dbClose(cv)
)
s3c1xGetd("AFTER-TRIGGER" list('dbDeleteObj 'dbDeleteInst 'geDeleteSel 'schDelete 'geDelete 'schDeleteFig
                               'dbDestroy 'hiDeleteWindow 'schCreateWire 'dbCreateWire 'schWire
                               'hiCreateWindow 'hiGetWindow 'hiGetEditWin 'hiGetSession
                               'hiPrint 'hiPrintBitmap 'hiSaveSnapshot 'hiGetGraphicWinExtent
                               'geCreateRect 'geCreateRectangles 'schMoveInst 'geMoveFig 'schSaveView
                               'schOpen 'hiCheckAndSave 'schCheck 'dbSetWindowDisplay 'hiRedraw
                               'dbSaveEntity 'hiEditWin))
printf("S3C1X-WINDOW %L session=%L editwin=%L\n" errset(hiGetWindow) car(errset(hiGetSession))
       car(errset(hiGetEditWin)))
printf("S3C1X_DONE\n")
exit()
