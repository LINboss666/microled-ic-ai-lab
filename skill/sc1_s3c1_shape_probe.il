; SCAN-1 S3-C1 section 2, second read-only pass: what graphics are REALLY in the eight symbols and
; the eight schematics, and which object-copy entry points this build offers.
;
; Why this pass exists: the corrected read-back already showed that the S3-C conclusion was built on
; the wrong attributes. cv->terms is empty while cv->terminals holds the ports (with name, direction
; and net) on BOTH views; and sym->figures is empty while sym->shapes holds 13 to 31 shapes per
; symbol -- the vendor p33:symbol behaves the same way (figures empty, 24 shapes). So "the importer
; made symbols with no graphics" and "directions cannot be read or kept in batch" are withdrawn here
; and replaced by shape-by-shape data. Whether those shapes amount to a usable body, pin and label
; set is decided from what this file prints, not from a guess.
;
; Read-only: every open is "r", nothing is created, moved or saved. The copy and setter entry points
; are only looked up with getd, never called.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_shape_probe.il 900 S3C1S_DONE
printf("S3C1S-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
CELLS_STR = "c2mos_dff sc1_scan_gate sc1_ls_core_r2d sc1_ls_c1_r2d sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_s3b_p33_bank_7 sc1_scan_power_1ch_s3c"
CELLS = car(errset(parseString(CELLS_STR " ")))

procedure(s3c1Val(obj slot)
  car(errset(dbGet(obj slot)))
)

procedure(s3c1FigCell(fig cellName viewName owner)
  let((lbl)
    printf("S3C1-SHAPE %L:%L owner=%L objType=%L lpp=%L layer=%L purpose=%L bbox=%L name=%L\n"
           cellName viewName owner s3c1Val(fig "objType") s3c1Val(fig "lpp")
           s3c1Val(fig "layer") s3c1Val(fig "purpose") s3c1Val(fig "bBox") s3c1Val(fig "name"))
    lbl = car(errset(fig->objName))
    when(lbl printf("S3C1-FIGNAME %L:%L owner=%L objName=%L\n" cellName viewName owner lbl))
    when(s3c1Val(fig "objType") == "label"
      printf("S3C1-LABEL %L:%L owner=%L text=%L just=%L high=%L rotation=%L\n" cellName viewName
             owner s3c1Val(fig "theLabel") s3c1Val(fig "justification") s3c1Val(fig "hiLabel")
             s3c1Val(fig "rotation")))
  )
)

procedure(s3c1ProbeView(cellName viewName)
  let((cv shape pinObj termObj fig)
    cv = car(errset(dbOpenCellViewByType(LIB cellName viewName nil "r")))
    unless(cv printf("S3C1S-OPEN-FAILED %L %L\n" cellName viewName))
    when(cv
      printf("S3C1S-VIEW %L %L viewName=%L terminals=%L shapes=%L nets=%L\n" cellName viewName
             s3c1Val(cv "viewName") car(errset(length(s3c1Val(cv "terminals"))))
             car(errset(length(s3c1Val(cv "shapes")))) car(errset(length(s3c1Val(cv "nets")))))
      foreach(shape s3c1Val(cv "shapes")
        s3c1FigCell(shape cellName viewName "cellview"))
      foreach(termObj s3c1Val(cv "terminals")
        foreach(pinObj s3c1Val(termObj "pins")
          printf("S3C1-PIN %L:%L term=%L pinDir=%L figs=%L\n" cellName viewName
                 s3c1Val(termObj "name") s3c1Val(pinObj "direction")
                 car(errset(length(s3c1Val(pinObj "figs")))))
          foreach(fig s3c1Val(pinObj "figs")
            s3c1FigCell(fig cellName viewName s3c1Val(termObj "name")))
        )
      )
      dbClose(cv)
    )
  )
)

foreach(cellName CELLS
  s3c1ProbeView(cellName "symbol")
  s3c1ProbeView(cellName "schematic")
)

printf("S3C1S-COPYAPI ddCopyCell=%L dbCopyCell=%L dbCopyCellView=%L dbCreateCellView=%L ddCreateCell=%L dbSetq=%L dbSave=%L dbCreateShape=%L dbCreateRect=%L dbCreateLabel=%L dbMoveFig=%L dbDeleteObj=%L dbCreateNet=%L dbSetInstBBox=%L dbChangeCellViewMaster=%L schCheck=%L dbGetBBox=%L dbCreateFigFig=%L\n"
       getd('ddCopyCell) getd('dbCopyCell) getd('dbCopyCellView) getd('dbCreateCellView)
       getd('ddCreateCell) getd('dbSetq) getd('dbSave) getd('dbCreateShape) getd('dbCreateRect)
       getd('dbCreateLabel) getd('dbMoveFig) getd('dbDeleteObj) getd('dbCreateNet)
       getd('dbSetInstBBox) getd('dbChangeCellViewMaster) getd('schCheck) getd('dbGetBBox)
       getd('dbCreateFigFig))
printf("S3C1S_DONE\n")
exit()
