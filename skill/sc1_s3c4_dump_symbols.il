;; sc1_s3c4_dump_symbols.il -- read-only inventory of every Symbol port and the text drawn next to it.
;;
;; Why this round exists: six hand-taken native screenshots were submitted and reviewed (S3C4 task
;; book), and the finding is that the NAME text next to a pin does not belong to that pin -- the top
;; Symbol shows "clk" near the bottom ground pin while "vss" sits top-right, the Xchain instance in
;; the top schematic shows "blank" inside a pin wired to vss, Xff shows "vdd" on a vss pin, Xcore
;; shows "x" on a vss pin. S3C2's s2aFindAxis matched labels to pins BY COORDINATE only, so its
;; 48/48 geometric result never proved the text belongs to the terminal it labels.
;;
;; So this file answers, per Symbol view, reading nothing but the database:
;;   1. cv~>terminals -> the real name and direction of each port (frozen this round);
;;   2. term~>pins~>figs -> the electrical pin rectangle, plus the pin's own terminal name to prove
;;      ownership of that rectangle instead of assuming it;
;;   3. the children of each pin figure -> the label / textDisplay attached to it, printed with every
;;      candidate text attribute (theLabel / text / strings / val / name), because "the attribute is
;;      not nil" is not a correspondence proof and reading the wrong field prints the field, not the
;;      displayed text;
;;   4. every label / textDisplay / text shape in the view, attached or loose, so an orphan stub or a
;;      duplicated name is visible in the data;
;;   5. the figures on device/drawing (symbol body and the short stubs) with their points, because a
;;      stub has to connect the body to ITS pin rectangle;
;;   6. the view's own objName, which must survive the fix.
;;
;; The name<->text correspondence is built offline from this dump and only then applied. Nothing is
;; moved here and nothing is saved; views open mode "r". NEW_SIMULATION_RUNS = 0.

sdLib = "microled_scan_s3c"
;; a wrapper may pre-set sdCells (the copy-proof run dumps only the copy); the default is every
;; Symbol view in the delivered library, which is also what the AFTER readback uses.
;; measured: `unless(sdCells ...)` aborts with `*Error* eval: unbound variable - sdCells` in this
;; SKILL build, so the test has to be boundp on the quoted name
unless(boundp('sdCells)
  sdCells = list("sc1_scan_power_1ch_s3c" "sc1_r3_scan_chain_1ch" "sc1_ls_c1_top_r2d"
                 "sc1_ls_core_r2d" "sc1_ls_c1_r2d" "sc1_scan_gate" "c2mos_dff"
                 "sc1_s3b_p33_bank_7" "s3c_asg_shell")
)

procedure(sdVal(v) if(v v "NONE"))
procedure(sdLen(x) if(x length(x) 0))
procedure(sdGet(o nm) car(errset(dbGet(o nm))))

procedure(sdText(tag o)
  printf("%s objType=%L layer=%L purpose=%L xy=%L bbox=%L theLabel=%L text=%L strings=%L val=%L name=%L just=%L assoc=%L\n"
         tag sdVal(o~>objType) sdGet(o 'layerName) sdGet(o 'purpose) sdGet(o 'xy) sdGet(o 'bBox)
         sdGet(o 'theLabel) sdGet(o 'text) sdGet(o 'strings) sdGet(o 'val) sdGet(o 'name)
         sdGet(o 'justification) sdGet(o 'assoc))
)

printf("SD-BEGIN\n")
foreach(cell sdCells
  cv = car(errset(dbOpenCellViewByType(sdLib cell "symbol" nil "r")))
  printf("SD-VIEW %L opened=%L terminals=%L shapes=%L objName=%L\n"
         cell sdVal(cv != nil) sdLen(if(cv cv~>terminals nil)) sdLen(if(cv cv~>shapes nil))
         sdGet(cv 'objName))
  when(cv
    foreach(tm cv~>terminals
      printf("SD-TERM %L name=%L direction=%L pins=%L\n"
             cell sdVal(tm~>name) sdVal(tm~>direction) sdLen(tm~>pins))
      foreach(p tm~>pins
        foreach(f p~>figs
          printf("SD-PINFIG %L term=%L objType=%L layer=%L purpose=%L bbox=%L owner=%L children=%L\n"
                 cell sdVal(tm~>name) sdVal(f~>objType) sdGet(f 'layerName) sdGet(f 'purpose)
                 sdGet(f 'bBox) sdVal(sdGet(sdGet(f 'pin) 'name)) sdLen(sdGet(f 'children)))
          foreach(ch sdGet(f 'children)
            sdText(sprintf(nil "SD-CHILD %L %L" cell sdVal(tm~>name)) ch)
          )
        )
      )
    )
    foreach(s cv~>shapes
      when(or(equal(s~>objType "label") equal(s~>objType "textDisplay") equal(s~>objType "text"))
        sdText(sprintf(nil "SD-TXT %L" cell) s)
      )
    )
    foreach(s cv~>shapes
      when(or(equal(sdGet(s 'layerName) "device") equal(sdGet(s 'layerName) "drawing"))
        printf("SD-GRAPH %L objType=%L layer=%L purpose=%L bbox=%L xy=%L pts=%L numpts=%L\n"
               cell sdVal(s~>objType) sdGet(s 'layerName) sdGet(s 'purpose) sdGet(s 'bBox)
               sdGet(s 'xy) sdGet(s 'points) sdLen(sdGet(s 'points)))
      )
    )
    errset(dbClose(cv))
  )
)
printf("SD-DONE\n")
nil
