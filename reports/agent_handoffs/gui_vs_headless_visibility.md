# GUI vs headless visibility -- SCAN-UNIT-VIS-REGISTER-R1

Question this answers: the user reported "从仓库拉取的电路没有注册到 Virtuoso". Does that mean the
library is unregistered, or does it mean something else? Two sessions and one machine are involved,
so the answer has to be written as a matrix, not as a single sentence.

## 1. The machine and the session

One guest only. `hostname` = `work-eda`, RHEL6.5, IC617 6.1.7-64b. The Windows host reaches it over
ssh key auth through the repo wrapper `scripts/guest.sh ssh`. There is no second Cadence working
environment on this machine that could be the one the user means: `ps` + `/proc` show exactly one
editor process, and the three sibling launch logs in the same minute all died on "log file already
locked", which is what repeated shortcut clicks produce.

| | the session the user sees | the batch session this round ran |
| --- | --- | --- |
| launched by | `/root/Desktop/MicroLED-IC-Project.desktop` -> `cadence_work/launch_virtuoso.sh` | `scripts/sch_virtuoso.sh` (same launcher family, MODE=nograph) |
| process | PID 15224, start **11:34:09** (state as measured that evening; the user closed it cleanly at 21:30:55 — see the addendum note in §4), log last written 20:52 | PID varied, ran 21:19, exited by itself |
| binary | `<IC617>/tools/dfII/bin/64bit/virtuoso` | same, with `-nograph` |
| cwd | `<PROJ>/cadence_work` (read from `/proc/15224/cwd`) | `<PROJ>/cadence_work` (runner forces it) |
| `-cdslib` | absent from `/proc/15224/cmdline` | absent |
| `CDS_LIB_PATH` | absent from `/proc/15224/environ` | absent |
| HOME | `/root` | `<PROJ>/cadence_work/home` |
| **library map in force** | **`cadence_work/cds.lib`** | **`cadence_work/cds.lib`** |

Cadence resolves `cds.lib` from the session's **working directory**, so the two sessions read the
same map. HOME only selects the `.cdsinit` and the session's own scratch; `/root/cds.lib` and
`/root/.cds.lib` do not exist on this guest, so nothing in HOME could override the map. The rows
that would matter for "am I looking at a different environment" -- cwd, `-cdslib`, `CDS_LIB_PATH`,
existence of a competing map in HOME -- are identical, and each was read out of `/proc`, not assumed.

One genuinely different map does exist on this box, `<DESKTOP>/cds.lib` (6 lines, dated Oct 3,
SOFTINCLUDE of the IC617 share plus `LDO_P`, `opamp_60dB`, `mile_two_stage`, `microled_dirver`,
`microled_dirver0`). It is in force only when a session starts with `cwd=/root/Desktop`. Alongside
it sit `libManager.log`, `libManager.log.1` and two `libManager.log*.cdslck` from that older habit.
Anyone who still starts Virtuoso that way sees five libraries and none of the project's -- which
would produce exactly the reported sentence. It is not what PID 15224 is doing.

## 2. Registration state of the map, and the timing that decides the diagnosis

`cadence_work/cds.lib` measured today: 636 B, sha256 `b3712feb…c5a8`, **mtime 02:31:59**.
Seven `DEFINE`, no `INCLUDE`/`SOFTINCLUDE`, no repeated library name, six original definitions
untouched, and exactly one added line for `sc1_s3c_team_pretty` pointing at an absolute path that
exists and is readable. The pre-write backup `cds.lib.bak.20261015_023159_libreg` (364 B) is beside it.

**The registration write (02:31:59) is earlier than the GUI launch (11:34:09) on the same day.**
A running session never re-reads the map, but this session had not started yet when the line was
written, so it read the DEFINE at launch. "Registered but the open window is stale" is therefore
ruled out by measurement. `scripts/sc1_libreg_team.sh` re-run would print `ALREADY_REGISTERED` and
leave the hash unchanged; that is the idempotency case the script was written for.

## 3. Visibility matrix

| layer | what was asked | answer | grade | evidence |
| --- | --- | --- | --- | --- |
| Git | is the OA in the repository? | **NO** -- `*.oa`, `cds.lib`, `cdsinfo.*`, `data.dm` are all gitignored; Git carries netlists, goldens, scripts and logs | DIRECTLY_VERIFIED | `.gitignore`, `git diff --name-only 9049f11..HEAD` |
| Git | is there anything at all to pull for this circuit? | YES, six frozen masters, four goldens, the rebuild + verify tools | DIRECTLY_VERIFIED | section A of the inventory |
| disk | is the OA on this guest? | YES -- 8 cells x (schematic+symbol) = 16 views + 1 build-shell view, 17 `.oa`, mode 755, **zero `.cdslck` inside the library** | DIRECTLY_VERIFIED | inventory section D |
| disk | is it on *another* guest / workspace? | NO -- one guest, one map, path inside the same `$WORK` | DIRECTLY_VERIFIED | inventory section B/C |
| map | is it DEFINEd in the map the GUI reads? | YES -- one line, correct absolute path, no same-name/different-path conflict | DIRECTLY_VERIFIED | inventory section C |
| run time, **headless** | does a session with the shortcut's cwd resolve it, and do all 16 views open? | **YES -- `LIBVIS: PASS`, `views_opened=16 of 16`, `ddGetObj` -> `dd:0x179e1f90`, schCheck errors 0 x8, dbCheck t x8** | REPRODUCED (re-run today 21:19, numbers identical to the accepted 02:42 run) | `results/evidence/sc1_unit_r1_libvis_remeasure.txt` |
| run time, **the user's GUI** | is the library actually in front of the user in PID 15224? | **NOT_VERIFIED -> WAITING_USER** | -- | see section 4 |

The last row is the whole substance of this report. Everything above it says the registration is
correct and complete; it still is not the same statement as "the user can see it in the window they
have open", and the task book forbids collapsing the two.

## 4. What the GUI side does and does not show so far

Measured about PID 15224, read-only, without touching it:

* `grep -c "sc1_s3c_team_pretty"` over its session log = **0**. In this session the library has never
  been opened, named or queried. That is consistent with "registered, resolved, never looked at", and
  inconsistent with "opened and found broken".
* No window titled Library Manager is open among its 23 X windows; the visible titles are ADE L (4)
  dialogs (`Choosing Analyses`, `Setting Outputs`, `Saving State`), `spectre3: Save/Select Results`,
  `Transient Options`, `Open File`, `Descend`, `Edit Object Properties`. The user is mid-simulation
  in someone else's task, with modal dialogs up.
* The user's own cells are **write-locked right now**: `microled_cells/c2mos_dff_1bit_pretty`
  schematic and symbol, and `c2mos_dff_1bit_pretty_tb` schematic, all with `.cdslck` mtimes at
  20:51:40. Their work is open and dirty.

Consequence for method: the only honest way to fill the last row is one read-only action **by the
user** in that session. This agent will not inject SKILL into someone else's live session and will
not restart it, because both could discard unsaved ADE state. The two queries below are read-only
and take ten seconds; the CIW is `Windows -> CIW` (or the Cadence Input line of any Virtuoso window).

```skill
ddGetObj("sc1_s3c_team_pretty")
```

* a handle like `dd:0x…`  -> the library is in this session's list and resolves. Registered.
* `nil`                  -> it is not in this session's list, and the next line says whether the
  list itself was read before or after 02:31:59.

```skill
member("sc1_s3c_team_pretty" ddGetLibList()~>name)
```

* non-nil (it returns the tail of the list starting at the match) -> present in the live lib list.
* `nil` with a non-nil `ddGetObj` above -> report both, do not reconcile them yourself.
* if `~>` throws in this build, the equivalent without the property operator is
  `member("sc1_s3c_team_pretty" setof(n ddGetLibList() n->name))`.

Then, in Library Manager: type or filter the name `sc1_s3c_team_pretty` -- **not**
`microled_scan_s3c`, which does not exist on this guest (section 5) -- and open
`sc1_scan_power_1ch_s3c`, view `schematic`, then view `symbol`.

If the user prefers not to touch a session that is mid-simulation, the agreed fallback is to record
`USER_GUI_VISIBILITY = WAITING_USER_GUI` and stop at Gate 1, which is what this round does.

> **Addendum, same evening.** The user closed PID 15224 themselves at **21:30:55** -- the log ends with
> `hiQuit()` then `hiDBoxOK(hiQuitDBox)` then `# Memory report: on exit … 13:30:55.387` (UTC), and
> afterwards `ps` shows no editor process and `xwininfo` shows 0 Virtuoso windows. This was not caused by
> this round: the only two guest actions after 21:00 were the read-only batch session that opened every
> view with mode `"r"` and exited itself, and a repeat of the registration script that printed
> `ALREADY_REGISTERED` and wrote nothing. `cds.lib` sha256 is still `b3712feb…c5a8` and the delivered
> library still holds zero locks. What changes is the method: there is no live session to intrude on now,
> so the two queries above are run in a **freshly launched shortcut session** -- which reads the map at its
> own start, and therefore reads the DEFINE that has been in place since 02:31:59. One stale write-lock
> survives on the user's own `microled_cells/c2mos_dff_1bit_pretty/schematic` (mtime 20:51:40, no holder);
> it was left in place deliberately, and removing it is the user's decision. Verbatim record:
> `results/evidence/sc1_unit_r1_addendum_session_closed.txt`.

## 5. The most likely cause of the reported sentence

Ranked by how well each fits the measurements:

1. **Name mismatch, not a registration failure.** The delivered library is called
   `sc1_s3c_team_pretty`. The source-side machine's library is `microled_scan_s3c`, and `find` over
   the whole guest proves that name exists **nowhere here**; it is not in Git either, because OA is
   gitignored by design. Meanwhile `microled_cells` -- the library the user actually works in --
   contains **no** scan cell at all (`grep -iE "sc1|scan|bank|level|r3"` -> NONE). So "I pulled the
   repo and the circuits are not registered" is exactly what a search under the old name, or a glance
   inside `microled_cells`, would report -- while the OA is registered under its own new name.
   Grade: strongly supported (the absence measurements are DIRECTLY_VERIFIED; the user's search
   intent is inferred).
2. **The library was simply never opened in this session.** Log mentions = 0. Grade: DIRECTLY_VERIFIED
   as a fact; as an explanation it is consistent with 1 rather than independent.
3. **An older habit of launching from `/root/Desktop`.** That map has five unrelated libraries and its
   own stale Library-Manager locks. Grade: DIRECTLY_VERIFIED that the map and locks exist; NOT_VERIFIED
   that it is what the user looked at today.
4. Ruled out by measurement: OA absent from disk (it is there, unlocked); OA on another guest; wrong or
   duplicated path in the live map (one DEFINE, valid path); missing PDK dependency (`smic18mmrf`
   directory with `tech.db` present); stale cache in the open session (write 02:31:59 < launch 11:34:09).
   `git push` status is not part of this question and was not used as an answer to it.

## 6. Two claims this report deliberately does not make

* It does **not** claim the user's Library Manager shows the library. `GATE1_HEADLESS_VISIBLE = PASS`
  and `USER_GUI_VISIBILITY = WAITING_USER` are separate cells on purpose.
* It does **not** claim any presentation result. No symbol pin, body outline or pin name was moved,
  no leaf or parent sheet was rearranged, no copy library was created, and therefore
  `PRESENTATION = NOT_DONE` and `ELECTRICAL_EQUIVALENCE_AFTER = NOT_RUN`. The electrical verdict still
  rests on the previous round's evidence, so it is labelled `PREVIOUS_EVIDENCE`, not re-claimed here.
