# -*- coding: utf-8 -*-
"""DATA-7A-R3: the publish / recover transaction regression.

    python scripts/dd1_d7a_publish_test.py

Every case gets its own fresh fixture under `review/dd1_d7a/publish_recovery_test/` and the official
`results/evidence/` set is only ever read: its digest map is taken before and after the whole run and
any change is a failure of this script. No case here is a design judgement -- the subject is the
delivery tool in `dd1_d7a_run.py`.

rc=0 means the repaired behaviour held. The defects this script exists because of are the reviewer's
T2 negatives (`probe_publish_recovery.py`, rc=0 = reproduced), which are NOT what PASS means here:
here every case also states the stage it reached, the refusal that came out, the marker and backup
state and the file set before and after.

Two cases call the real entry `do_export()` with `build_artefacts` replaced by a stub; they are
labelled BOUNDARY_DIAGNOSTIC and prove only the entry's recovery precondition, never a build.
"""
from __future__ import print_function

import hashlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7a_check as ck                                        # noqa: E402
import dd1_d7a_run as R                                           # noqa: E402

NAMES = ['dd1_d7a_cases.csv', 'dd1_d7a_control_cases.csv', 'dd1_d7a_manifest.json']
OLD = dict((n, u'OLD_BYTES %s\n' % n) for n in NAMES)
NEW = dict((n, u'NEW_BYTES %s\n' % n) for n in NAMES)
FOREIGN = 'unrelated_other_phase.csv'
FOREIGN_STAGE = 'other_transactions_file.csv.new'
FIXTURE_ROOT = os.path.join(PROJ, 'review', 'dd1_d7a', 'publish_recovery_test')


class Interrupt(BaseException):
    """a crash at an exact boundary: the caught-failure rollback must not see it"""


class BuilderReached(Exception):
    """raised by the stubbed builder in the BOUNDARY_DIAGNOSTIC cases"""


def digests(d):
    return dict((n, R.sha256(os.path.join(d, n))) for n in sorted(os.listdir(d))
                if os.path.isfile(os.path.join(d, n)))


def short(m):
    return dict((k, v[:12]) for k, v in sorted(m.items()))


def seed(ev, files=OLD, extra_foreign=True):
    if os.path.isdir(ev):
        shutil.rmtree(ev)
    os.makedirs(ev)
    for name, text in sorted(files.items()):
        with io.open(os.path.join(ev, name), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(text if isinstance(text, str) else text)
    if extra_foreign:
        with io.open(os.path.join(ev, FOREIGN), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u'A file that belongs to no publish transaction at all\n')
        with io.open(os.path.join(ev, FOREIGN_STAGE), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u'A staging file left there by some other phase\n')


class Case(object):
    """one fixture: its own evidence directory, its own backup directory, its own assertions"""

    def __init__(self, name, phase=''):
        self.name = name
        self.phase = phase
        self.dir = os.path.join(FIXTURE_ROOT, name)
        self.ev = os.path.join(self.dir, 'evidence')
        self.bak = os.path.join(self.dir, 'a_run_dir', 'publish_backup')
        self.rows = []
        self.refusal = ''
        self.rc = None
        seed(self.ev)
        R.EVIDENCE = self.ev

    def check(self, label, ok, detail=''):
        self.rows.append((label, bool(ok), str(detail)[:150]))

    def state(self):
        files = digests(self.ev)
        marker = os.path.exists(os.path.join(self.ev, R.PENDING_MARKER))
        pending = R.pending_publish()
        backups = sorted(os.listdir(self.bak)) if os.path.isdir(self.bak) else []
        own_left = [n for n in files if (n.endswith('.new') or n.endswith('.restore'))
                    and n[:-4] in NAMES]
        return {'files': len(files), 'marker': marker, 'own_staging_left': own_left,
                'pending': ('invalid' if (pending or {}).get('marker_invalid')
                            else ('none' if pending is None else 'outstanding')),
                'backup_files': backups}

    def finish(self):
        before = dict((n, hashlib.sha256(('%sOLD_BYTES %s\n' % ('', n)).encode('utf-8')).hexdigest()[:12])
                      for n in NAMES)
        after = short(digests(self.ev))
        st = self.state()
        changed = sorted(n for n in NAMES if before.get(n) != after.get(n)
                         or before.get(n) is None)
        return {'case': self.name, 'phase': self.phase, 'rc': self.rc, 'refusal': self.refusal,
                'marker': st['marker'], 'pending': st['pending'],
                'backup_files': st['backup_files'], 'own_staging_left': st['own_staging_left'],
                'files_changed_from_old': changed,
                'foreign_file_kept': os.path.exists(os.path.join(self.ev, FOREIGN)),
                'foreign_stage_kept': os.path.exists(os.path.join(self.ev, FOREIGN_STAGE)),
                'rows': self.rows}


def publish_expect_raise(case, art=NEW, backup=None, promote=None, patch=None):
    """run publish(), remember the refusal and the process return-code equivalent"""
    original = None
    if patch:
        original = patch[0]()
    try:
        R.publish(art, backup_dir=backup or case.bak, promote=promote)
        case.rc = 0
        case.refusal = ''
        return False
    except ck.Refuse as exc:
        case.rc = 1
        case.refusal = str(exc)
        return True
    except Exception as exc:                                       # noqa: BLE001
        case.rc = 99
        case.refusal = 'UNCAUGHT %s: %s' % (type(exc).__name__, exc)
        return False
    finally:
        if original is not None:
            patch[1](original)


def staging_fail_at(n):
    """patch R._fsync_write so the n-th .new write throws a catchable OSError"""
    holder = {}

    def install():
        holder['old'] = R._fsync_write
        seen = []

        def patched(path, data):
            if str(path).endswith('.new'):
                seen.append(os.path.basename(str(path)))
                if len(seen) == n:
                    raise OSError('INJECTED staging write failure on %s' % seen[-1])
            return holder['old'](path, data)
        R._fsync_write = patched
        return holder['old']

    def restore(old):
        R._fsync_write = old
    return (install, restore)


def marker_write_fail():
    holder = {}

    def install():
        holder['old'] = R._fsync_write

        def patched(path, data):
            if str(path).endswith(R.PENDING_MARKER):
                raise OSError('INJECTED marker write failure')
            return holder['old'](path, data)
        R._fsync_write = patched
        return holder['old']

    def restore(old):
        R._fsync_write = old
    return (install, restore)


def restore_write_fail():
    holder = {}

    def install():
        holder['old'] = R._fsync_write

        def patched(path, data):
            if str(path).endswith('.restore'):
                raise OSError('INJECTED restore-write failure')
            return holder['old'](path, data)
        R._fsync_write = patched
        return holder['old']

    def restore(old):
        R._fsync_write = old
    return (install, restore)


def backup_copy_fail():
    holder = {}

    class BrokenShutil(object):
        @staticmethod
        def copyfile(src, dst):
            raise OSError('INJECTED backup copy failure')

        @staticmethod
        def rmtree(path):
            shutil.rmtree(path)

    def install():
        holder['old'] = R.shutil
        R.shutil = BrokenShutil
        return holder['old']

    def restore(old):
        R.shutil = old
    return (install, restore)


def interrupt_promote(at, after=True, exc=None):
    """a promotion primitive that fails on the at-th call, as a crash (BaseException) or caught I/O"""
    calls = []
    exc = exc or Interrupt

    def promote(src, dst):
        calls.append(os.path.basename(dst))
        if after:
            os.replace(src, dst)
            if len(calls) == at:
                raise exc('INJECTED failure after promotion %d' % at)
        else:
            if len(calls) == at:
                raise exc('INJECTED failure before promotion %d' % at)
            os.replace(src, dst)
    return promote, calls


def crash_publish(case, at, after=True, art=NEW, names_expected=None):
    promote, calls = interrupt_promote(at, after)
    try:
        R.publish(art, backup_dir=case.bak, promote=promote)
    except Interrupt:
        pass
    if names_expected is not None:
        case.check('the crash landed between promotions', calls == names_expected,
                   'promotions=%s' % calls)


# ------------------------------------------------------------------ the cases
def case_normal():
    c = Case('normal_publish', 'promotion+verify+cleanup')
    before = digests(c.ev)
    ok = publish_expect_raise(c)
    c.check('a normal publish does not raise', not ok, c.refusal)
    after = digests(c.ev)
    for n in NAMES:
        want = hashlib.sha256(NEW[n].encode('utf-8')).hexdigest()
        c.check('%s holds the new bytes' % n, after.get(n) == want, str(after.get(n))[:12])
        c.check('%s backup holds the old bytes' % n,
                R.sha256(os.path.join(c.bak, n)) == before[n], before[n][:12])
    st = c.state()
    c.check('no marker survives', not st['marker'], st['pending'])
    c.check('no own staging file survives', not st['own_staging_left'], st['own_staging_left'])
    c.check('the unrelated file of another phase is untouched',
            after.get(FOREIGN) == before.get(FOREIGN), 'unchanged')
    return c.finish()


def case_promotion_failures():
    out = []
    for at, label in ((1, 'publish_fail_first'), (2, 'publish_fail_middle'),
                      (len(NAMES), 'publish_fail_last')):
        c = Case(label, 'promotion %d fails' % at)
        before = digests(c.ev)
        promote, calls = interrupt_promote(at, after=False, exc=OSError)
        ok = publish_expect_raise(c, promote=promote)
        c.check('the publish is refused, not left to escape', ok, c.refusal[:90])
        c.check('the refusal counts the promotions that landed',
                'publish aborted after %d/%d promotion(s)' % (min(at, len(NAMES)) - 1, len(NAMES))
                in c.refusal, c.refusal[:90])
        c.check('the previous set is restored byte for byte', digests(c.ev) == before,
                str(short(digests(c.ev)))[:90])
        st = c.state()
        c.check('the marker is cleared after a verified rollback', not st['marker'], st['pending'])
        c.check('no staging file of this transaction survives', not st['own_staging_left'],
                st['own_staging_left'])
        c.rc = 1
        out.append(c.finish())
    return out


def case_staging_failure():
    c = Case('staging_write_fails', 'staging write #2 fails')
    before = digests(c.ev)
    ok = publish_expect_raise(c, patch=staging_fail_at(2))
    c.check('the staging failure is refused', ok, c.refusal[:90])
    c.check('the refusal says nothing was promoted',
            'publish stopped before the first promotion' in c.refusal, c.refusal[:90])
    c.check('the published set is untouched', digests(c.ev) == before, str(short(digests(c.ev)))[:90])
    st = c.state()
    c.check('the marker does not survive a pre-promotion stop', not st['marker'], st['pending'])
    c.check('no .new of this transaction survives', not st['own_staging_left'],
            st['own_staging_left'])
    c.check('the unrelated foreign staging file is NOT swept',
            os.path.exists(os.path.join(c.ev, FOREIGN_STAGE)), 'kept for its own phase')
    return c.finish()


def case_marker_write_failure():
    c = Case('marker_write_fails', 'marker write fails')
    before = digests(c.ev)
    ok = publish_expect_raise(c, patch=marker_write_fail())
    c.check('the marker write failure is refused', ok, c.refusal[:90])
    c.check('nothing was promoted', 'publish stopped before the first promotion' in c.refusal,
            c.refusal[:90])
    c.check('no half-written marker is left to be mistaken for an empty transaction',
            not os.path.exists(os.path.join(c.ev, R.PENDING_MARKER)), str(c.state()))
    c.check('the published set is untouched', digests(c.ev) == before, str(short(digests(c.ev)))[:90])
    return c.finish()


def case_backup_prepare_failure():
    c = Case('backup_prepare_fails', 'backup copy fails')
    before = digests(c.ev)
    ok = publish_expect_raise(c, patch=backup_copy_fail())
    c.check('the backup preparation failure is refused', ok, c.refusal[:90])
    c.check('the refusal names the stage', 'publish stopped before the first promotion' in c.refusal,
            c.refusal[:90])
    c.check('the published set is untouched', digests(c.ev) == before, str(short(digests(c.ev)))[:90])
    st = c.state()
    c.check('no marker and no staging file survives', not st['marker'] and not st['own_staging_left'],
            str(st)[:90])
    return c.finish()


def case_rollback_also_fails():
    c = Case('rollback_write_fails', 'promotion fails and the rollback fails too')
    before = digests(c.ev)
    promote, calls = interrupt_promote(2, after=False, exc=OSError)
    original = R._fsync_write

    def fail_restore(path, data):
        if str(path).endswith('.restore'):
            raise OSError('INJECTED rollback write failure')
        return original(path, data)
    R._fsync_write = fail_restore
    try:
        ok = publish_expect_raise(c, promote=promote)
    finally:
        R._fsync_write = original
    c.check('the double failure is refused', ok, c.refusal[:90])
    c.check('the refusal says the rollback itself failed', 'ROLLBACK ITSELF FAILED' in c.refusal,
            c.refusal[:120])
    st = c.state()
    c.check('the transaction is NOT reported as recovered', st['marker'] and
            st['pending'] == 'outstanding', str(st)[:90])
    refused = ''
    try:
        R.publish(NEW, backup_dir=os.path.join(c.dir, 'must_not_be_used'))
    except ck.Refuse as exc:
        refused = str(exc)[:80]
    c.check('a new publish is refused while the rollback failed set is outstanding', bool(refused),
            refused)
    # now the condition is repaired: the same transaction must recover completely
    rec = R.recover_publish()
    c.check('recover_publish() then restores the whole set', rec.get('complete') is True,
            json.dumps(dict((k, rec[k]) for k in ('complete', 'restored', 'failed', 'marker_kept')),
                       sort_keys=True)[:140])
    c.check('the recovered set is byte-identical to the old one', digests(c.ev) == before,
            str(short(digests(c.ev)))[:90])
    c.check('the marker is only cleared by a verified recovery', not c.state()['marker'],
            str(c.state())[:90])
    return c.finish()


def case_recorded_backup():
    c = Case('interrupt_nondefault_backup', 'crash mid-promotion, recovery with no argument')
    before = digests(c.ev)
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    st = c.state()
    c.check('the interrupted publish left its marker', st['marker'], str(st)[:90])
    rec = R.recover_publish()                                 # exactly how do_export calls it
    c.check('recovery used the backup named by the marker',
            rec.get('backup_used') == R._record_path(c.bak), str(rec.get('backup_used')))
    c.check('recovery completed', rec.get('complete') is True, json.dumps(rec, sort_keys=True)[:140])
    for n in NAMES:
        c.check('%s is byte-identical to the old generation' % n,
                digests(c.ev).get(n) == before[n], str(digests(c.ev).get(n))[:12])
    st = c.state()
    c.check('the marker is gone once the whole set verified', not st['marker'], st['pending'])
    c.check('this transaction\'s staging files are gone', not st['own_staging_left'],
            st['own_staging_left'])
    c.check('the foreign staging file of another phase is kept',
            os.path.exists(os.path.join(c.ev, FOREIGN_STAGE)), 'kept')
    return c.finish()


def case_missing_backup():
    c = Case('one_backup_missing', 'recovery with a backup the crash cannot satisfy')
    before = digests(c.ev)
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    os.remove(os.path.join(c.bak, NAMES[0]))
    first, second = R.recover_publish(), R.recover_publish()
    for tag, rec in (('first', first), ('second', second)):
        c.check('%s recovery reports incomplete' % tag, rec.get('complete') is False,
                json.dumps(dict((k, rec[k]) for k in ('complete', 'failed', 'marker_kept')),
                           sort_keys=True)[:140])
        c.check('%s recovery keeps the marker' % tag, rec.get('marker_kept') is True,
                str(rec.get('reason'))[:120])
    c.check('the outstanding transaction is still identified after both retries',
            R.pending_publish() is not None and not R.pending_publish().get('marker_invalid'),
            str(c.state())[:90])
    refused = ''
    try:
        R.publish(NEW, backup_dir=os.path.join(c.dir, 'must_not_be_used'))
    except ck.Refuse as exc:
        refused = str(exc)[:80]
    c.check('a new publish is refused instead of overwriting the backup/marker', bool(refused),
            refused)
    with io.open(os.path.join(c.bak, NAMES[0]), 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(OLD[NAMES[0]])                                # the operator supplies the backup
    third = R.recover_publish()
    c.check('with the backup whole, the same transaction recovers', third.get('complete') is True,
            json.dumps(dict((k, third[k]) for k in ('complete', 'restored', 'failed')),
                       sort_keys=True)[:140])
    c.check('the whole old set is verified', digests(c.ev) == before, str(short(digests(c.ev)))[:90])
    c.check('and only then is the marker cleared', not c.state()['marker'], str(c.state())[:90])
    return c.finish()


def case_wrong_digest_backup():
    c = Case('backup_digest_wrong', 'a backup that is present but is not the recorded bytes')
    before = digests(c.ev)
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    with io.open(os.path.join(c.bak, NAMES[1]), 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(u'SOME_OTHER_GENERATION\n')
    rec = R.recover_publish()
    c.check('the mismatching backup is refused', rec.get('complete') is False,
            json.dumps(dict((k, rec[k]) for k in ('complete', 'failed')), sort_keys=True)[:140])
    c.check('the refusal names the digest that disagrees',
            any('hashes to' in f for f in rec.get('failed', [])), str(rec.get('failed'))[:120])
    c.check('the marker is kept', rec.get('marker_kept') is True and c.state()['marker'],
            str(c.state())[:90])
    with io.open(os.path.join(c.bak, NAMES[1]), 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(OLD[NAMES[1]])
    rec2 = R.recover_publish()
    c.check('a correct backup completes the same transaction', rec2.get('complete') is True,
            json.dumps(dict((k, rec2[k]) for k in ('complete', 'restored', 'failed')),
                       sort_keys=True)[:140])
    c.check('the old set is byte-identical again', digests(c.ev) == before,
            str(short(digests(c.ev)))[:90])
    return c.finish()


def case_restore_write_fails():
    c = Case('restore_write_fails', 'recovery itself cannot write')
    before = digests(c.ev)
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    holder = {}
    holder['old'] = R._fsync_write

    def fail(path, data):
        if str(path).endswith('.restore'):
            raise OSError('INJECTED write failure during recovery')
        return holder['old'](path, data)
    R._fsync_write = fail
    try:
        first = R.recover_publish()
    finally:
        R._fsync_write = holder['old']
    c.check('the failed write is reported, not swallowed', first.get('complete') is False,
            json.dumps(dict((k, first[k]) for k in ('complete', 'failed')), sort_keys=True)[:140])
    c.check('it names restoring as the failing step',
            any('restoring it raised' in f for f in first.get('failed', [])),
            str(first.get('failed'))[:120])
    c.check('the marker is kept so the next run is refused too', first.get('marker_kept') is True,
            str(c.state())[:90])
    second = R.recover_publish()
    c.check('retrying once the write works completes it', second.get('complete') is True,
            json.dumps(dict((k, second[k]) for k in ('complete', 'restored', 'failed')),
                       sort_keys=True)[:140])
    c.check('the old set is restored byte for byte', digests(c.ev) == before,
            str(short(digests(c.ev)))[:90])
    return c.finish()


def case_corrupt_markers():
    out = []
    for shape in ('bad_json', 'missing_fields', 'wrong_types', 'not_an_object', 'contradicts',
                  'bad_digest_form', 'unknown_schema'):
        c = Case('marker_%s' % shape, 'an unusable marker is presented')
        good = {'schema': R.MARKER_SCHEMA, 'phase': R.MARKER_PHASE, 'files': NAMES,
                'backup': R._record_path(c.bak),
                'previous': dict((n, hashlib.sha256(OLD[n].encode('utf-8')).hexdigest())
                                 for n in NAMES),
                'absent': []}
        text = {'bad_json': u'{NOT_VALID_JSON',
                'not_an_object': json.dumps([]),
                'missing_fields': json.dumps({'phase': R.MARKER_PHASE, 'files': NAMES}),
                'wrong_types': json.dumps(dict(good, files='not-a-list')),
                'contradicts': json.dumps(dict(good, absent=['dd1_d7a_negative.csv'])),
                'bad_digest_form': json.dumps(dict(good, previous=dict((n, 'zzz') for n in NAMES))),
                'unknown_schema': json.dumps(dict(good, schema='d7a-publish/99'))}[shape]
        os.makedirs(c.bak)
        for n in NAMES:                            # the backup this transaction would have prepared
            with io.open(os.path.join(c.bak, n), 'w', encoding='utf-8', newline='\n') as fp:
                fp.write(OLD[n])
        before = digests(c.ev)
        with io.open(os.path.join(c.ev, NAMES[0]), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(NEW[NAMES[0]])                            # a mixed set, as a crash would leave it
        with io.open(os.path.join(c.ev, R.PENDING_MARKER), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(text if isinstance(text, str) else text)
        damaged = digests(c.ev)
        state = R.pending_publish()
        c.check('the marker is reported as unusable, not as no transaction',
                bool((state or {}).get('marker_invalid')), str(state)[:120])
        rec = R.recover_publish()
        c.check('recovery refuses it instead of calling it complete',
                rec.get('needed') is True and rec.get('complete') is False,
                json.dumps(dict((k, rec[k]) for k in ('needed', 'complete', 'marker_kept')),
                           sort_keys=True)[:120])
        c.check('the marker survives the refusal', os.path.exists(os.path.join(c.ev, R.PENDING_MARKER)),
                str(c.state())[:90])
        c.check('the damaged set is not rewritten or renamed', digests(c.ev) == damaged,
                str(short(digests(c.ev)))[:90])
        refused = ''
        try:
            R.publish(NEW, backup_dir=c.bak)
        except ck.Refuse as exc:
            refused = str(exc)[:80]
        c.check('a new publish is refused over an unusable marker', bool(refused), refused)
        # the recoverable condition completed: write the marker this transaction should have left
        with io.open(os.path.join(c.ev, R.PENDING_MARKER), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(json.dumps(good, sort_keys=True))
        rec2 = R.recover_publish()
        c.check('with a readable record the same transaction recovers',
                rec2.get('complete') is True and digests(c.ev) == before,
                json.dumps(dict((k, rec2[k]) for k in ('complete', 'restored', 'failed')),
                           sort_keys=True)[:120])
        c.rc = 1
        out.append(c.finish())
    return out


def case_absent_target():
    c = Case('previously_absent_target', 'crash after the new target was promoted')
    os.remove(os.path.join(c.ev, NAMES[-1]))                   # legitimately did not exist before
    before = digests(c.ev)
    crash_publish(c, len(NAMES), after=True, names_expected=NAMES)
    state = R.pending_publish()
    c.check('the marker records that target as previously absent',
            NAMES[-1] in (state or {}).get('absent', []), str((state or {}).get('absent')))
    c.check('no digest was taken of a file that does not exist',
            NAMES[-1] not in (state or {}).get('previous', {}), str(sorted((state or {})
                                                                          .get('previous', {})))[:90])
    c.check('the crash did publish the new target', os.path.exists(os.path.join(c.ev, NAMES[-1])),
            'present before recovery')
    rec = R.recover_publish()
    c.check('recovery puts it back to not-existing',
            rec.get('complete') is True and not os.path.exists(os.path.join(c.ev, NAMES[-1])),
            json.dumps(dict((k, rec[k]) for k in ('complete', 'restored', 'failed')),
                       sort_keys=True)[:140])
    c.check('the other targets are the old bytes', digests(c.ev) == before,
            str(short(digests(c.ev)))[:90])
    c.check('the marker is cleared', not c.state()['marker'], str(c.state())[:90])
    return c.finish()


def case_caller_disagrees():
    c = Case('caller_backup_disagrees', 'a caller hands over the wrong backup directory')
    before = digests(c.ev)
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    wrong = os.path.join(c.dir, 'a_global_default_backup')
    os.makedirs(wrong)
    rec = R.recover_publish(backup_dir=wrong)
    c.check('the recorded directory is used, not the one the caller guessed',
            rec.get('backup_used') == R._record_path(c.bak), str(rec.get('backup_used')))
    c.check('the disagreement itself keeps the transaction open',
            rec.get('complete') is False and any('recorded' in f for f in rec.get('failed', [])),
            str(rec.get('failed'))[:140])
    c.check('the marker is kept', rec.get('marker_kept') is True and c.state()['marker'],
            str(c.state())[:90])
    rec2 = R.recover_publish()
    c.check('asked correctly the second time it closes', rec2.get('complete') is True,
            json.dumps(dict((k, rec2[k]) for k in ('complete', 'failed')), sort_keys=True)[:120])
    c.check('and the old set is verified', digests(c.ev) == before, str(short(digests(c.ev)))[:90])
    return c.finish()


def case_entry_precondition():
    """BOUNDARY_DIAGNOSTIC: the real do_export() gate, with the artefact builder stubbed

    The builder is replaced by a sentinel/stub so that the case can say which side of the recovery
    gate the entry reached. It proves nothing about building or about a real export PASS.
    """
    out = []
    c = Case('entry_export_refused', 'do_export with an outstanding transaction (BOUNDARY_DIAGNOSTIC)')
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    as_crashed = digests(c.ev)
    os.remove(os.path.join(c.bak, NAMES[0]))                   # make the recovery genuinely impossible
    reached = []

    def stub_builder(run_dir):
        reached.append(run_dir)
        raise BuilderReached('the builder must not be reached while a transaction is outstanding')
    real_builder = R.build_artefacts
    R.build_artefacts = stub_builder
    try:
        rc = R.do_export({'out': c.dir})
    finally:
        R.build_artefacts = real_builder
    c.rc = rc
    c.check('do_export returns non-zero', rc == 1, 'rc=%s' % rc)
    c.check('the builder was never reached', not reached, str(reached)[:90])
    c.check('the unfinished transaction is still on disk', c.state()['marker'], str(c.state())[:90])
    c.check('the refusal did not rewrite anything it could not verify',
            all(as_crashed.get(k) == v for k, v in digests(c.ev).items()),
            str(sorted(k for k, v in digests(c.ev).items() if as_crashed.get(k) != v))[:90])
    gone = sorted(set(as_crashed) - set(digests(c.ev)))
    c.check('the only files that disappeared are this transaction\'s own staging files',
            all(k in [n + '.new' for n in NAMES] for k in gone) and FOREIGN_STAGE not in gone,
            'gone=%s' % gone[:90])
    c.check('and it created none of its own', not sorted(set(digests(c.ev)) - set(as_crashed)),
            str(sorted(set(digests(c.ev)) - set(as_crashed)))[:90])
    out.append(c.finish())

    c = Case('entry_export_proceeds', 'do_export after a completed recovery (BOUNDARY_DIAGNOSTIC)')
    crash_publish(c, 2, after=False, names_expected=NAMES[:2])
    rec = R.recover_publish()
    c.check('the outstanding transaction closes first', rec.get('complete') is True,
            json.dumps(dict((k, rec[k]) for k in ('complete', 'failed')), sort_keys=True)[:120])
    art = dict((n, NEW[n]) for n in NAMES)
    real_builder, real_guard = R.build_artefacts, R.write_guard_report
    R.build_artefacts = lambda run_dir: art
    R.write_guard_report = lambda run_dir: u('stub: guard not re-run in this boundary case\n')
    rc = None
    try:
        rc = R.do_export({'out': c.dir})
    finally:
        R.build_artefacts, R.write_guard_report = real_builder, real_guard
    c.rc = rc
    c.check('a clean evidence directory lets the entry publish', rc == 0, 'rc=%s' % rc)
    after = digests(c.ev)
    for n in NAMES:
        c.check('%s holds the published bytes' % n,
                after.get(n) == hashlib.sha256(NEW[n].encode('utf-8')).hexdigest(),
                str(after.get(n))[:12])
    c.check('the entry left no marker behind', not c.state()['marker'], str(c.state())[:90])
    out.append(c.finish())
    return out


def main():
    real_ev = R.EVIDENCE
    official = digests(real_ev) if os.path.isdir(real_ev) else {}
    if os.path.isdir(FIXTURE_ROOT):
        shutil.rmtree(FIXTURE_ROOT)
    results = []
    try:
        results.append(case_normal())
        results.extend(case_promotion_failures())
        results.append(case_staging_failure())
        results.append(case_marker_write_failure())
        results.append(case_backup_prepare_failure())
        results.append(case_rollback_also_fails())
        results.append(case_recorded_backup())
        results.append(case_missing_backup())
        results.append(case_wrong_digest_backup())
        results.append(case_restore_write_fails())
        results.extend(case_corrupt_markers())
        results.append(case_absent_target())
        results.append(case_caller_disagrees())
        results.extend(case_entry_precondition())
    finally:
        R.EVIDENCE = real_ev
    print('DATA-7A-R3 publish / recover transaction regression')
    print('fixtures: review/dd1_d7a/publish_recovery_test/<case>, the official evidence directory is '
          'never a target')
    print('')
    bad_cases, bad_rows = 0, 0
    for r in results:
        ok = all(x[1] for x in r['rows'])
        if not ok:
            bad_cases += 1
        print('%-4s %-32s phase=%-46s rc=%s marker=%s pending=%s changed=%s own_staging=%s '
              'foreign=%s/%s'
              % ('PASS' if ok else 'FAIL', r['case'], r['phase'][:46], r['rc'], r['marker'],
                 r['pending'], r['files_changed_from_old'], r['own_staging_left'],
                 r['foreign_file_kept'], r['foreign_stage_kept']))
        if r['refusal']:
            print('       refusal: %s' % r['refusal'][:150])
        for label, held, detail in r['rows']:
            if not held:
                bad_rows += 1
                print('       FAILED CHECK %-52s %s' % (label[:52], detail))
    now = digests(real_ev) if os.path.isdir(real_ev) else {}
    touched = sorted(k for k in set(official) | set(now) if official.get(k) != now.get(k))
    print('')
    print('official evidence directory before/after: %d files, changed=%s'
          % (len(official), touched or 'none'))
    print('PUBLISH_RECOVERY_TEST: %s (%d cases, %d failed checks)'
          % ('PASS' if not bad_cases and not touched else 'FAIL (%d cases)' % bad_cases,
             len(results), bad_rows))
    return 0 if (not bad_cases and not touched) else 1


if __name__ == '__main__':
    sys.exit(main())
