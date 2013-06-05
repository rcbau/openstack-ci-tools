#!/usr/bin/python

# Pull work entries off the queue and execute them

import imp
import os
import socket

import utils

# Valid work done statuses:
#    y = work done
#    m = plugin not found


if __name__ == '__main__':
    cursor = utils.get_cursor()
    worker = socket.gethostname()

    try:
        (ident, number, workname) = utils.dequeue_work(cursor, worker)

        # Load plugins
        plugins = []
        for ent in os.listdir('plugins'):
            if ent[0] != '.' and ent.endswith('.py'):
                plugin_info = imp.find_module(ent[:-3], ['plugins'])
                plugins.append(imp.load_module(ent[:-3], *plugin_info))

        handled = False
        for plugin in plugins:
            handled = plugin.ExecuteWork(cursor, ident, number, workname, worker)
            if handled:
                cursor.execute('update work_queue done="y" where id="%s" and '
                               'number=%s and workname="%s";'
                               % (ident, number, workname))
                cursor.execute('commit;')
                break

        if not handled:
            utils.log(cursor, worker, ident, number, workname,
                      'No plugin found for work of %s type' % workname)
            cursor.execute('update work_queue done="m" where id="%s" and '
                           'number=%s and workname="%s";'
                           % (ident, number, workname))
            cursor.execute('commit;')

    except utils.NoWorkFound:
        pass
