#!/usr/bin/python

# Pull work entries off the queue and execute them

import imp
import os
import socket

import utils

# Valid work done statuses:
#    y = work done
#    m = plugin not found
#    c = git conflict during checkout


if __name__ == '__main__':
    cursor = utils.get_cursor()
    worker = socket.gethostname()

    try:
        while True:
            (ident, number, workname, attempt) = utils.dequeue_work(cursor,
                                                                    worker)
            print '=========================================================='
            utils.clear_log(cursor, ident, number, workname, attempt)

            # Checkout the patchset
            change = utils.get_patchset_details(cursor, ident, number)
            conflict = True
            rewind = 0

            while conflict and rewind < 10:
                git_repo, conflict = utils.create_git(change['project'],
                                                      change['refurl'],
                                                      cursor, worker, ident,
                                                      number, workname, rewind)
                if conflict:
                    utils.log(cursor, worker, ident, number, workname, attempt,
                              'Git merge failure with HEAD~%d' % rewind)
                    rewind += 1

            if conflict:
                utils.log(cursor, worker, ident, number, workname, attempt,
                          'Git merge failure detected')
                cursor.execute('update work_queue set done="c" '
                               'where id="%s" and number=%s and workname="%s" '
                               'and attempt %s;'
                               % (ident, number, workname,
                                  utils.format_attempt_criteria(attempt)))
                cursor.execute('commit;')
                continue

            utils.log(cursor, worker, ident, number, workname, attempt,
                      'Git checkout created')

            # Load plugins
            plugins = []
            for ent in os.listdir('plugins'):
                if ent[0] != '.' and ent.endswith('.py'):
                    plugin_info = imp.find_module(ent[:-3], ['plugins'])
                    plugins.append(imp.load_module(ent[:-3], *plugin_info))

            handled = False
            for plugin in plugins:
                handled = plugin.ExecuteWork(cursor, ident, number, workname,
                                             worker, attempt)
                if handled:
                    cursor.execute('update work_queue set done="y" '
                                   'where id="%s" and '
                                   'number=%s and workname="%s" '
                                   'and attempt %s;'
                                  % (ident, number, workname,
                                     utils.format_attempt_critera(attempt)))
                    cursor.execute('commit;')
                    break

            if not handled:
                utils.log(cursor, worker, ident, number, workname, attempt,
                          'No plugin found for work of %s type' % workname)
                cursor.execute('update work_queue set done="m" where '
                               'id="%s" and number=%s and workname="%s" and '
                               'attempt %s;'
                               % (ident, number, workname,
                                  utils.format_attempt_criteria(attempt)))
                cursor.execute('commit;')

    except utils.NoWorkFound:
        pass
