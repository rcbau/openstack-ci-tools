#!/usr/bin/python

# Pull work entries off the queue and execute them

import imp
import os
import socket

import workunit
import utils


if __name__ == '__main__':
    cursor = utils.get_cursor()
    worker = socket.gethostname()
    constraints = utils.get_config.get(constraints, '')

    try:
        while True:
            work = workunit.dequeue_work(cursor, worker, constraints)
            print '=========================================================='
            work.clear_log(cursor)

            # Checkout the patchset
            change = utils.get_patchset_details(cursor, ident, number)
            conflict = True
            rewind = 0

            while conflict and rewind < 10:
                git_repo, conflict = utils.create_git(change['project'],
                                                      change['refurl'],
                                                      cursor, work, rewind)
                if conflict:
                    work.log(cursor, 'Git merge failure with HEAD~%d' % rewind)
                    rewind += 1

            if conflict:
                work.log(cursor, 'Git merge failure detected')
                work.set_conflict(cursor)
                continue

            work.log(cursor, 'Git checkout created')

            # Load plugins
            plugins = []
            for ent in os.listdir('plugins'):
                if ent[0] != '.' and ent.endswith('.py'):
                    plugin_info = imp.find_module(ent[:-3], ['plugins'])
                    plugins.append(imp.load_module(ent[:-3], *plugin_info))

            handled = False
            for plugin in plugins:
                handled = plugin.ExecuteWork(cursor, work, git_repo, change)
                if handled:
                    work.set_done(cursor)
                    break

            if not handled:
                work.log(cursor,
                         'No plugin found for work of %s type' % workname)
                work.set_missing(cursor)

    except workunit.NoWorkFound:
        pass
