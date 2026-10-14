; DATA-6 section 8: write the declared port directions onto the real OA terminal objects.
;
; Why this file exists in this task: spiceIn imported all eight cells with correct connectivity but
; gave EVERY terminal the direction inputOutput (measured in the independent read-back: 12 rows for
; c2mos_dff, all inputOutput, while the netlist declares d/clk input, q/qbar output, vdd/vss
; inputOutput). The task book requires schematic and symbol ports to carry the same names, directions
; and interface order, so the declared directions are written on the terminals themselves from the
; table scripts/dd1_d6_golden.py generated out of the masters -- not typed here.
;
; The mechanism is the one scan S3-C1 measured on this build and is copied by value from
; skill/sc1_s3c1_apply_dirs.il (which stays untouched): the attribute is `terminals' on BOTH views,
; the assignment form works while dbSetq returns nil, the schematic editor package only loads after a
; drawing call has been attempted, and the row count is enforced so a short table cannot half-fix a
; cell. Only microled_data_d6 is opened for write; the PDK and every pre-existing library are read-only.
;
; Run: S3C1_DIRS=/root/microled_ai_project/cadence_work/data_d6_oa/asg_in/dd1_d6_dir_table.gen.il \
;      bash scripts/dd1_d6_run_oa.sh /root/microled_ai_project/cadence_work/data_d6_oa/skill/dd1_d6_apply_dirs.il 900 D6D_DONE
printf("D6D-BEGIN\n")
LIB = car(errset(getShellEnvVar("S3C_LIB")))
LIB = if(LIB LIB "microled_data_d6")
DIRS = car(errset(getShellEnvVar("S3C1_DIRS")))
when(DIRS load(DIRS))
loaded = car(errset(s3c1DirTable))
printf("D6D-TABLE %L rows=%L\n" loaded car(errset(length(loaded))))
EXPECT_ITEMS = 47
EXPECT_WRITES = 92
; the generated file is `list(nil row row ...)', so the leading nil is one of the items. Counted by
; walking the table: `length(cdr loaded)' came back nil on this build, and a guard that prints a
; wrong count is worse than no guard. The count is re-checked against the read-back afterwards.
table_items = 0
foreach(row s3c1DirTable table_items = table_items + 1)
printf("D6D-ROWS items=%L expect=%L (46 declared ports plus the leading nil)\n" table_items
       EXPECT_ITEMS)
when(loaded == nil printf("D6D-REFUSE no direction table loaded -- nothing is written\n"))
when(and(loaded != nil table_items != EXPECT_ITEMS)
  printf("D6D-REFUSE the table has %L items, not the %L expected\n" table_items EXPECT_ITEMS))
CELLS_ENV = car(errset(getShellEnvVar("S3C_CELLS")))
CELLS_STR = if(CELLS_ENV CELLS_ENV
               "c2mos_dff sc1_scan_gate dd1_inv18 dd1_control_1ch data_sink_1ch data_bias_ref dd1_sink_unit_1ch dd1_data_top_1ch")
CELLS = car(errset(parseString(CELLS_STR " ")))
printf("D6D-LIB %L CELLS %L\n" LIB CELLS)

procedure(d6dDir(cellName portName)
  let((out)
    out = nil
    foreach(row s3c1DirTable
      when(and(nth(0 row) == cellName nth(1 row) == portName) out = nth(2 row)))
    out
  )
)

; `intern' on this build wants a symbol, not a string, so the declared spellings are mapped to the
; direction symbols by hand
procedure(d6dSym(want)
  cond(
    (want == "input" 'input)
    (want == "output" 'output)
    (t 'inputOutput)
  )
)

procedure(d6dNorm(x)
  let((s)
    s = errset(symname(x))
    if(car(s) car(s) x)
  )
)

procedure(d6dTouchEditor(cv)
  ; a wrong-arity dbCreateRect raises inside errset and that is what pulls schematic.cxt in
  let((r)
    r = errset(dbCreateRect(cv list(list(0.0 0.0) list(0.1 0.1))))
    printf("D6D-LOADTRIGGER %L schCheck=%L schCreateWire=%L\n" car(r) getd('schCheck)
           getd('schCreateWire))
  )
)

matched = 0
views_done = 0
foreach(cellName CELLS
  foreach(viewName list("schematic" "symbol")
    cv = car(errset(dbOpenCellViewByType(LIB cellName viewName
                                        if(viewName == "schematic" "schematic" nil) "a")))
    unless(cv printf("D6D-OPEN-FAILED %L %L\n" cellName viewName))
    when(cv
      if(views_done == 0 d6dTouchEditor(cv))
      foreach(termObj cv->terminals
        want = d6dDir(cellName termObj->name)
        if(want == nil
          printf("D6D-UNDECLARED %L:%L %L has no row in the golden port table\n"
                 cellName viewName termObj->name)
          let((before after)
            before = car(errset(termObj->direction))
            termObj->direction = d6dSym(want)
            after = car(errset(termObj->direction))
            if(d6dNorm(after) == want
              matched = matched + 1)
            printf("D6D %L %L port=%L before=%L want=%L after=%L norm=%L\n" cellName viewName
                   termObj->name before want after d6dNorm(after))
          )
        )
      )
      printf("D6D-SAVE %L %L %L\n" cellName viewName errset(dbSave(cv)))
      when(getd('schCheck)
        printf("D6D-SCHCHECK %L %L => %L\n" cellName viewName errset(schCheck(cv))))
      views_done = views_done + 1
      dbClose(cv)
    )
  )
)
printf("D6D-VIEWS %L MATCHED %L WANT %L\n" views_done matched EXPECT_WRITES)
unless(and(views_done == 16 matched == EXPECT_WRITES)
  printf("D6D-INCOMPLETE views=%L matched=%L\n" views_done matched))
printf("D6D_DONE\n")
