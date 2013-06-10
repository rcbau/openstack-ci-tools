#!/usr/bin/python

# Dump logs of jobs to a web server

import cgi
import os
import re

import utils


UPGRADE_BEGIN_RE = re.compile('\*+ DB upgrade to state of (.*) starts \*+')
UPGRADE_END_RE = re.compile('\*+ DB upgrade to state of (.*) finished \*+')


if __name__ == '__main__':
    cursor = utils.get_cursor()
    subcursor = utils.get_cursor()
    cursor.execute('select * from work_queue where done is not null;')
    for row in cursor:
        path = os.path.join('/var/www/ci', row['id'], str(row['number']), row['workname'])
        workerpath = os.path.join(path, 'worker')
        worker = None
        if os.path.exists(workerpath):
            with open(workerpath, 'r') as f:
                worker = f.read().rstrip()

        if worker != row['worker']:
            print path
            if not os.path.exists(path):
                os.makedirs(path)
            with open(workerpath, 'w') as f:
                f.write(row['worker'])
            with open(os.path.join(path, 'state'), 'w') as f:
                f.write(row['done'])
            with open(os.path.join(path, 'log.html'), 'w') as f:
                buffered = []
                upgrades = []
                in_upgrade = False

                subcursor.execute('select * from work_logs where id="%s" and number=%s and workname="%s" and worker="%s" order by timestamp asc;'
                                  %(row['id'], row['number'], row['workname'], row['worker']))
                linecount = 0
                f.write('<html><head><title>%(id)s -- %(number)s</title>\n'
                        '<link rel="stylesheet" type="text/css" href="/style.css" />\n'
                        '</head><body>\n'
                        '<h1>CI run for %(id)s, patchset %(number)s</h1>\n'
                        % {'id': row['id'],
                           'number': row['number']})
                for logrow in subcursor:
                    m = UPGRADE_BEGIN_RE.match(logrow['log'])
                    if m:
                         upgrades.append('<li><a href="#%(name)s">Upgrade to %(name)s</a>'
                                         % {'name': m.group(1)})
                         buffered.append('<a name="%s"></a>' % m.group(1))
                         in_upgrade = True

                    line = ('<a name="%(linenum)s"></a><a href="#%(linenum)s">#</a> '
                            % {'linenum': linecount})
                    if in_upgrade:
                        line += '<b>'
                    line += ('%(timestamp)s %(line)s'
                             % {'timestamp': logrow['timestamp'],
                                'line': cgi.escape(logrow['log'].rstrip())})
                    if in_upgrade:
                        line += '</b>'
                    buffered.append(line)

                    linecount += 1

                    m = UPGRADE_END_RE.match(logrow['log'])
                    if m:
                         in_upgrade = False

                f.write('<ul>%s</ul>' % ('\n'.join(upgrades)))
                f.write('<pre><code>\n')
                f.write('\n'.join(buffered))
                f.write('</code></pre></body></html>')
