; SCAN-1 S3-C1 section 2: the CORRECTED read-only readback.
;
; What the previous pass got wrong, and why it matters. S3-C printed the schematic ports from
; cv->terms and the symbol ports from sym->terminals, read the symbol content from
; dbGet(sym "figures"), and then concluded that batch sessions cannot carry pin directions and that
; importer symbols hold no graphics at all. Those two accessors are not the same object, and one
; attribute is not the whole cellview: a nil from the wrong attribute is not evidence of absence.
; So this file
;   * reads TERMINALS on both views (cellView.terminals) with name, direction and the net behind
;     each terminal, plus the pins / term-view figures each terminal really owns;
;   * counts figures, shapes, instances, nets and labels SEPARATELY, and distinguishes
;     SUPPORTED-BUT-EMPTY from UNSUPPORTED (an attribute that raises) from COUNT=n;
;   * re-tests the drawing and editor entry points AFTER the target views have been opened, because
;     an application package can load late -- getd nil at startup alone proves nothing;
;   * prints objType/viewType so every number is tied to a kind of cellview.
;
; Two build-specific traps are avoided on purpose: the loop variable is never called t (t is the
; protected true in SKILL, measured in SCH-3), and no string is built with sprintf (this build
; answers 'argument #1 must be a symbol or nil' -- measured in S3-C), so names are printed as read.
;
; Strictly read-only: every open is mode "r"; nothing is created, moved, saved or deleted.
;
; Run: bash scripts/sc1_s3c_run_oa.sh /root/microled_ai_project/cadence_work/s3c_oa/skill/sc1_s3c1_readback.il 900 S3C1R_DONE
printf("S3C1R-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_scan_s3c")
CELLS_ENV = car(errset(getShellEnvVar("S3C_CELLS")))
CELLS_STR = if(CELLS_ENV CELLS_ENV
               "c2mos_dff sc1_scan_gate sc1_ls_core_r2d sc1_ls_c1_r2d sc1_ls_c1_top_r2d sc1_r3_scan_chain_1ch sc1_s3b_p33_bank_7 sc1_scan_power_1ch_s3c")
CELLS = car(errset(parseString(CELLS_STR " ")))
PDKLIB = "smic18mmrf"

; nil from errset = the attribute raised; (nil) = supported and empty; otherwise a real list
procedure(s3c1Attr(obj nm cellName viewName)
  let((res)
    res = errset(dbGet(obj nm))
    cond(
      (res == nil
       printf("S3C1-ATTR %L:%L %L => UNSUPPORTED_OR_RAISES\n" cellName viewName nm))
      (car(res) == nil
       printf("S3C1-ATTR %L:%L %L => EMPTY (supported, nothing in it)\n" cellName viewName nm))
      (t
       printf("S3C1-ATTR %L:%L %L => COUNT=%L\n" cellName viewName nm length(car(res))))
    )
  )
)

procedure(s3c1FigTypes(obj nm cellName viewName)
  let((res)
    res = car(errset(dbGet(obj nm)))
    when(res
      foreach(fig res
        printf("S3C1-FIG %L:%L attr=%L objType=%L lpp=%L layer=%L purpose=%L bbox=%L name=%L\n"
               cellName viewName nm car(errset(fig->objType)) car(errset(fig->lpp))
               car(errset(fig->layer->name)) car(errset(fig->layer->purpose))
               car(errset(fig->bBox)) car(errset(fig->objName)))
      )
    )
  )
)

procedure(s3c1Terminals(cv cellName viewName)
  let((lst termObj tvObj pinObj)
    lst = car(errset(dbGet(cv "terminals")))
    printf("S3C1-TERMS %L:%L terminals=%L\n" cellName viewName
           if(lst car(errset(length(lst))) "UNSUPPORTED"))
    when(lst
      foreach(termObj lst
        printf("S3C1-TERM %L:%L name=%L dir=%L net=%L objType=%L\n" cellName viewName
               car(errset(termObj->name)) car(errset(termObj->direction))
               car(errset(if(termObj->net termObj->net->name "-"))) car(errset(termObj->objType)))
        foreach(tvObj car(errset(termObj->termViews))
          printf("S3C1-TERMVIEW %L:%L term=%L dir=%L figs=%L labels=%L bbox=%L\n" cellName viewName
                 car(errset(termObj->name)) car(errset(tvObj->direction))
                 car(errset(length(car(errset(tvObj->figs)))))
                 car(errset(length(car(errset(tvObj->labels))))) car(errset(tvObj->bbox)))
          foreach(pinObj car(errset(tvObj->figs))
            printf("S3C1-TVFIG %L:%L term=%L objType=%L lpp=%L bbox=%L\n" cellName viewName
                   car(errset(termObj->name)) car(errset(pinObj->objType))
                   car(errset(pinObj->lpp)) car(errset(pinObj->bBox)))
          )
        )
        foreach(pinObj car(errset(termObj->pins))
          printf("S3C1-TERMPIN %L:%L term=%L objType=%L direction=%L figs=%L\n" cellName viewName
                 car(errset(termObj->name)) car(errset(pinObj->objType))
                 car(errset(pinObj->direction))
                 car(errset(length(car(errset(pinObj->figs))))))
          )
      )
    )
  )
)

procedure(s3c1View(cellName viewName)
  let((cv nm)
    cv = car(errset(dbOpenCellViewByType(LIB cellName viewName nil "r")))
    unless(cv printf("S3C1-OPEN-FAILED %L %L\n" cellName viewName))
    when(cv
      printf("S3C1-VIEW %L %L objType=%L viewType=%L\n" cellName viewName
             car(errset(cv->objType)) car(errset(dbGet(cv "viewType"))))
      foreach(nm list("terminals" "terms" "figures" "figs" "shapes" "instances" "nets" "labels")
        s3c1Attr(cv nm cellName viewName)
      )
      s3c1Terminals(cv cellName viewName)
      dbClose(cv)
    )
  )
)

procedure(s3c1Api(stage)
  foreach(fn list('dbCreateRect 'dbCreateLine 'dbCreateLabel 'dbCreatePolygon 'dbCreateEllipse
                  'dbCreatePath 'dbCreateFig 'dbMoveFig 'dbCopyFig 'dbCreateInst 'dbCreateTerm
                  'dbCreatePin 'dbCreateProp 'dbSetq 'dbSetBoundingFig 'schCheck 'schCreate
                  'schCreateSym 'symCreate 'schConvSch2Sym 'schMakeConvSym 'hiCreateWindow
                  'hiOpenView 'hiCheckAndSave 'synCheck 'schUseCheck)
    printf("S3C1-API %L %L=%L\n" stage fn getd(fn))
  )
)

s3c1Api("BEFORE-VIEWS")
foreach(cellName CELLS
  s3c1View(cellName "schematic")
  s3c1View(cellName "symbol")
)
s3c1Api("AFTER-VIEWS")

; the vendor's own symbol as the shape reference a reviewer can compare our symbols against
let((m nm)
  m = car(errset(dbOpenCellViewByType(PDKLIB "p33" "symbol" nil "r")))
  if(m == nil
    printf("S3C1-PDKREF p33:symbol OPEN-FAILED\n")
    let((done)
      printf("S3C1-PDKREF p33:symbol objType=%L\n" car(errset(m->objType)))
      foreach(nm list("terminals" "figures" "figs" "shapes")
        s3c1Attr(m nm "p33" "symbol"))
      s3c1Terminals(m "p33" "symbol")
      s3c1FigTypes(m "shapes" "p33" "symbol")
      s3c1FigTypes(m "figures" "p33" "symbol")
      dbClose(m)
      done = t
    )
  )
)
printf("S3C1R_DONE\n")
exit()
