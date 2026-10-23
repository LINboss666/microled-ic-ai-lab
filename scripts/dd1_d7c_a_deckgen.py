#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_deckgen.py -- the deck generator entry that DATA-7C-A must NOT use.

This round authorises no native launch and no deck publication. The generator exists so the next
round has one place to start from, and it is written so that the refusal happens before anything is
touched: no output directory is created, no file is opened for writing, no formal evidence path is
even resolved until after the authorisation test passes.

The refusal is a software boundary. It says nothing about whether the candidate netlist would run.
"""

from __future__ import absolute_import, print_function

import os
import sys

TASK_ID = 'DATA-7C-A'
NATIVE_AUTHORISED_THIS_ROUND = False
FORBIDDEN_OUTPUTS = ('results/evidence', 'spectre', 'results')


class Refused(Exception):
    pass


def _hash_tree(path):
    import hashlib
    if not os.path.isdir(path):
        return None
    digest = hashlib.sha256()
    for dir_path, dirs, names in os.walk(path):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(dir_path, name)
            digest.update(os.path.relpath(full, path).replace(os.sep, '/').encode('utf-8'))
            with open(full, 'rb') as handle:
                digest.update(handle.read())
    return digest.hexdigest()


def generate(code, out_dir, env=None):
    """build one DC deck per PAM code into out_dir -- refused in this round, deliberately

    `out_dir` must be outside the repository's formal product paths even when authorised, so a run
    can never overwrite a published artefact in place.
    """
    env = env if env is not None else os.environ
    before = _hash_tree(out_dir)
    if not NATIVE_AUTHORISED_THIS_ROUND:
        raise Refused('%s: this round authorises no native launch and no deck publication; '
                      'NATIVE_AUTHORISED_THIS_ROUND is False and the task brief sets '
                      'NEW_SPECTRE_LAUNCH_LIMIT=0' % TASK_ID)
    if env.get('QODER_SIM_AUTHORISED') != '1' or env.get('DATA7C_NATIVE_RUN') != '1':
        raise Refused('%s: native run flags absent (QODER_SIM_AUTHORISED/DATA7C_NATIVE_RUN)' % TASK_ID)
    for forbidden in FORBIDDEN_OUTPUTS:
        if os.path.abspath(out_dir).startswith(os.path.abspath(forbidden)):
            raise Refused('%s: refusing to write into the published path %s' % (TASK_ID, forbidden))
    if before is None:
        raise Refused('%s: refusing to create a simulation directory %s' % (TASK_ID, out_dir))
    # nothing past this line has been executed in DATA-7C-A; the next round fills the template in
    raise Refused('%s: deck template not implemented in this round (draft deck only, '
                  'spectre/dd1_d7c_a_tb_draft.scs)' % TASK_ID)


def probe(out_dir, env=None):
    """run the entry and report whether it refused and whether the directory is untouched"""
    env = env if env is not None else os.environ
    before = _hash_tree(out_dir)
    try:
        generate(0, out_dir, env)
    except Refused as error:
        after = _hash_tree(out_dir)
        return {'refused': True, 'reason': str(error), 'tree_before': before, 'tree_after': after,
                'untouched': before == after}
    return {'refused': False, 'reason': '', 'tree_before': before,
            'tree_after': _hash_tree(out_dir), 'untouched': False}


def main(argv):
    if '--probe' in argv:
        index = argv.index('--probe')
        target = argv[index + 1] if len(argv) > index + 1 else os.path.join(
            os.environ.get('TEMP', '/tmp'), 'dd1_d7c_a_deckgen_probe')
        if not os.path.isdir(target):
            os.makedirs(target)
        for path in (os.path.join(target, 'placeholder.txt'),):
            with open(path, 'w') as handle:
                handle.write('probe content\n')
        result = probe(target, dict(os.environ, QODER_SIM_AUTHORISED='1', DATA7C_NATIVE_RUN='1'))
        print('DECKGEN_PROBE refused=%s untouched=%s reason=%s'
              % (result['refused'], result['untouched'], result['reason'][:120]))
        return 0 if (result['refused'] and result['untouched']) else 1
    print('usage: python dd1_d7c_a_deckgen.py --probe <dir>   (this round can only refuse)')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
