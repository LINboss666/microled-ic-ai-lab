;; sc1_s3c1_gui1.il
;;
;; SCAN-1 S3C1 -- the one limited GUI session this task is allowed. It is used for the two things
;; the batch measurements showed batch cannot do: run the EDITOR's own check over the 16 views with
;; a real editor loaded, and put real Virtuoso views on screen so they can be captured.
;;
;; Established in batch, so nothing here re-explores it (readback/s3c1_probe*.log):
;;   * placement by assigning fig~>bBox and label~>xy WORKS and persists through dbSave + reopen
;;     (S7-SETBBOX rc=t changed=t / S7-SAVE t / S7-REOPEN t with the moved bbox);
;;   * dbMoveFig returned nil in three argument orders, dbCreateRect / dbCreateLine / dbCreateLabel
;;     / dbCreatePin returned nil in six forms, and dbDeleteObj / geMoveFig / schCreateWire /
;;     symUpdateInst are absent from the batch process.
;;
;; Order is deliberate: a window first (several editor functions only load once the editor really
;; opens), then the checks over all 16 views, then the four captures. Every step is errset-guarded
;; so one failure costs only itself, and views are opened read-only so nothing can prompt a save
;; form mid-session. This process belongs to the task (its own HOME, its own cds.lib, no user
;; window touched), so it closes itself. NEW_SIMULATION_RUNS = 0.

s8Lib    = "microled_scan_s3c"
s8Cells  = list("c2mos_dff" "sc1_scan_gate" "sc1_ls_core_r2d" "sc1_ls_c1_r2d"
                "sc1_ls_c1_top_r2d" "sc1_r3_scan_chain_1ch" "sc1_s3b_p33_bank_7"
                "sc1_scan_power_1ch_s3c")

s8WinNames = list('hiOpenView 'schOpen 'symOpen 'geOpen 'hiDisplayCellView 'schDisplayCellView
                  'geOpenCellView 'hiOpenCellView 'schOpenWindow 'symOpenWindow 'hiCreateWindow
                  'hiGetSession 'hiGetEditWin 'hiGetEditCellWindow 'geGetEditCellView
                  'hiGetWindowList 'hiGetWindow 'hiRedraw 'geFitAll 'hiZoomWholeWindow
                  'schFitAll 'hiCheckAndSave 'schCheck 'symCheck 'dbCheck 'system 'hiGetMainWindow)

procedure(s8Api(stage)
  let((n)
    foreach(n s8WinNames printf("S8-API %L %L %L\n" stage n getd(n)))
  )
)

procedure(s8Apply1(n arg)
  let((f)
    f = getd(n)
    if(f == nil nil car(errset(apply(f list(arg)))) != nil)
  )
)

procedure(s8Apply0(n)
  let((f)
    f = getd(n)
    if(f == nil nil car(errset(apply(f nil))) != nil)
  )
)

procedure(s8Open(cv)
  let((done)
    done = nil
    foreach(n list('hiOpenView 'schOpen 'symOpen 'geOpen 'hiDisplayCellView 'geOpenCellView
                   'hiOpenCellView 'schOpenWindow 'symOpenWindow)
      when(done == nil
        when(s8Apply1(n cv)
          printf("S8-OPEN-VIA %L\n" n)
          done = n
        )
      )
    )
    done
  )
)

procedure(s8Fit()
  let((done)
    done = nil
    foreach(n list('geFitAll 'schFitAll 'hiZoomWholeWindow)
      when(done == nil
        when(s8Apply0(n)
          printf("S8-FIT-VIA %L\n" n)
          done = n
        )
      )
    )
    done
  )
)

;; one view: open read-only, display, fit, then capture the window with a literal shell command.
;; The capture runs even when the display attempt failed: the script grabs the CIW and the graphics
;; window by id, so an undisplayed cellview still leaves a real record of this session rather than
;; nothing.
procedure(s8Shot(cell view kind cmd)
  let((cv win)
    cv = car(errset(dbOpenCellViewByType(s8Lib cell view
                                         if(view == "schematic" "schematic" nil) "r")))
    printf("S8-SHOT %L %L %L open=%L\n" cell view kind cv != nil)
    when(cv != nil
      win = s8Open(cv)
      printf("S8-SHOT %L displayed=%L\n" kind win != nil)
      s8Fit()
      when(getd('hiRedraw)
        printf("S8-SHOT %L redraw=%L\n" kind car(errset(hiRedraw(win))) != nil)
      )
      ;; the window must finish painting before it is grabbed
      printf("S8-SHOT %L capture=%L\n" kind car(errset(system(cmd))) != nil)
      dbClose(cv)
    )
  )
)

procedure(s8CheckOne(cell view)
  let((cv res)
    cv = car(errset(dbOpenCellViewByType(s8Lib cell view
                                         if(view == "schematic" "schematic" nil) "r")))
    printf("S8-CHK-OPEN %L %L %L\n" cell view cv != nil)
    when(cv != nil
      when(getd('schCheck)
        res = errset(schCheck(cv))
        printf("S8-SCHCHECK %L %L res=%L\n" cell view res)
      )
      when(getd('symCheck)
        res = errset(symCheck(cv))
        printf("S8-SYMCHECK %L %L res=%L\n" cell view res)
      )
      when(getd('dbCheck)
        res = errset(dbCheck(cv))
        printf("S8-DBCHECK %L %L res=%L\n" cell view res)
      )
      dbClose(cv)
    )
  )
)

printf("S8-BEGIN\n")
;; getshellenv is not defined in this build (measured: "*Error* eval: undefined function -
;; getshellenv" ended the first attempt of this session), so the display values are read by the
;; launcher in the shell and only reported from there.
s8Api("START")

;; ---- a window first, because the editor functions load with it ----------------------------
seed = car(errset(dbOpenCellViewByType(s8Lib "sc1_scan_power_1ch_s3c" "schematic" nil "r")))
printf("S8-SEED %L\n" seed != nil)
when(seed != nil
  printf("S8-SEED-DISPLAYED %L\n" s8Open(seed) != nil)
  s8Fit()
)
s8Api("AFTER-OPEN")
printf("S8-SESSION %L\n" if(getd('hiGetSession) car(errset(hiGetSession())) 'NO_FUNC))
printf("S8-EDITCELLVIEW %L\n" if(getd('geGetEditCellView) car(errset(geGetEditCellView()))
                                 'NO_FUNC))
when(getd('hiGetWindowList)
  printf("S8-WINLIST %L\n" errset(hiGetWindowList()))
)
;; the CIW is certainly painted at this point: it is the positive control that the session really
;; reached the X display, independent of whether a cellview could be displayed.
printf("S8-CAP-CIW %L\n"
       car(errset(system("bash /root/microled_ai_project/scripts/gui1_capture.sh s8_ciw"))) != nil)

;; ---- B: the editor's own check over all sixteen views -------------------------------------
foreach(cell s8Cells
  s8CheckOne(cell "schematic")
  s8CheckOne(cell "symbol")
)
printf("S8-CHECKS-DONE\n")

;; ---- C: four real views on screen ---------------------------------------------------------
;; literal shell strings: this SKILL's string handling is not trusted for concatenation here, and
;; the label is the only per-shot difference.
s8Shot("sc1_scan_power_1ch_s3c" "schematic" "top_sch"
       "sleep 2; bash /root/microled_ai_project/scripts/gui1_capture.sh s8_top_sch")
s8Shot("sc1_scan_power_1ch_s3c" "symbol" "top_sym"
       "sleep 2; bash /root/microled_ai_project/scripts/gui1_capture.sh s8_top_sym")
s8Shot("c2mos_dff" "schematic" "dff_sch"
       "sleep 2; bash /root/microled_ai_project/scripts/gui1_capture.sh s8_dff_sch")
s8Shot("sc1_s3b_p33_bank_7" "schematic" "bank_sch"
       "sleep 2; bash /root/microled_ai_project/scripts/gui1_capture.sh s8_bank_sch")

when(seed != nil dbClose(seed))
s8Api("END")
printf("S8-DONE\n")
exit()
