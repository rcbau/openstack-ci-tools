#!/usr/bin/python

"""Representation of a unit of work."""

# All code for the work_queue and work_logs tables should reside here.


import cgi
import datetime
import json
import _mysql
import os
import re
import uuid

import utils


LOG_HEADER = """<html><head><title>%(id)s -- %(number)s</title>
<link rel="stylesheet" type="text/css" href="/style.css" /></head><body>
<h1>CI run for %(id)s, patchset %(number)s</h1>
<p>What is this? This page shows the logs from a database upgrade continuous
integration run. Each patchset which proposes a database migration is run
against a set of test databases. This page shows the results for one of those
test databases. If the database is from Folsom, you will see a Grizzly
migration in the bullet list below. You should then see an upgrade to the
current state of trunk, and then finally the upgrade(s) contained in the
patchset. For more information, please contact
<a href="mailto:mikal@stillhq.com">mikal@stillhq.com</a>.</p>"""


# Remember that the timestamp isn't actually part of the log row!
UPGRADE_BEGIN_RE = re.compile('\*+ DB upgrade to state of (.*) starts \*+')
UPGRADE_END_RE = re.compile('\*+ DB upgrade to state of (.*) finished \*+')

GIT_CHECKOUT_RE = re.compile('/srv/git-checkouts/[a-z]+/'
                             '[a-z]+_refs_changes_[0-9_]+')
VENV_PATH_RE = re.compile('/home/mikal/\.virtualenvs/refs_changes_[0-9_]+')

MIGRATION_START_RE = re.compile('([0-9]+) -&gt; ([0-9]+)\.\.\.$')
MIGRATION_END_RE = re.compile('^done$')

FINAL_VERSION_RE = re.compile('Final schema version is ([0-9]+)')
MIGRATION_CLASH_RE = re.compile('Error: migration number .* appears '
                                'more than once')


class NoWorkFound(Exception):
    pass


def dequeue_work(cursor, worker, constraints):
    selectid = str(uuid.uuid4())
    cursor.execute('update work_queue set selectid="%s", worker="%s", '
                   'heartbeat = NOW() where selectid is NULL and '
                   'constraints="%s" limit 1;'
                   %(selectid, worker, constraints))
    cursor.execute('commit;')

    cursor.execute('select * from work_queue where selectid="%s";'
                   % selectid)
    if cursor.rowcount == 0:
        raise NoWorkFound()

    row = cursor.fetchone()
    w = WorkUnit(row['id'], row['number'], row['workname'],
                 row['attempt'], row['constraints'])
    w.worker = row['worker']
    return w


def recheck(cursor, ident, number, workname=None):
    if not workname:
        cursor.execute('select distinct(workname) from work_queue where '
                       'id="%s" and number=%s;'
                       %(ident, number))
        for row in cursor:
            recheck(cursor, ident, number, workname=row['workname'])
        return

    cursor.execute('select max(attempt) from work_queue where id="%s" and '
                   'number=%s and workname="%s";'
                   %(ident, number, workname))
    row = cursor.fetchone()
    attempt = row['max(attempt)']
    attempt += 1

    # This is a hard coded list for now to ensure a recheck of a pre-percona
    # job includes a percona run.
    constraints = ['mysql', 'percona']
    for constraint in constraints:
        cursor.execute('insert into work_queue(id, number, workname, '
                       'constraints, attempt) '
                       'values ("%s", %s, "%s", "%s", %s);'
                       %(ident, number, workname, constraint, attempt))
        cursor.execute('commit;')
        print 'Added recheck for %s %s %s %s' %(ident, number, workname,
                                                constraint)


def find_latest_attempts(cursor, ident, number, workname):
    constraints = []
    cursor.execute('select distinct(constraints) from work_queue where '
                   'id="%s" and number=%s and workname="%s";'
                   %(ident, number, workname))
    for row in cursor:
        constraints.append(row['constraints'])

    for constraint in constraints:
        cursor.execute('select max(attempt) from work_queue where id="%s" and '
                       'number=%s and workname="%s" and constraints="%s";'
                       %(ident, number, workname, constraint))
        row = cursor.fetchone()
        yield WorkUnit(ident, number, workname, row['max(attempt)'],
                       constraint)


class WorkUnit(object):
    def __init__(self, ident, number, workname, attempt, constraints):
        self.ident = ident
        self.number = number
        self.workname = workname
        self.attempt = attempt
        self.constraints = constraints
        self.worker = None

    def enqueue(self, cursor):
        cursor.execute('insert ignore into work_queue'
                       '(id, number, workname, constraints, attempt) '
                       'values ("%s", %s, "%s", "%s", %s);'
                       %(self.ident, self.number, self.workname,
                         self.constraints, self.attempt))
        cursor.execute('commit;')

    def heartbeat(self, cursor):
        cursor.execute('update work_queue set heartbeat=NOW() where '
                       'id="%s" and number=%s and workname="%s" and '
                       'worker="%s" and constraints="%s" and attempt=%s;'
                       %(self.ident, self.number, self.workname, self.worker,
                        self.constraints, self.attempt))
        cursor.execute('commit;')


    def clear_log(self, cursor):
        cursor.execute('delete from work_logs where id="%s" and number=%s and '
                       'workname="%s" and constraints="%s" and attempt=%s;'
                       %(self.ident, self.number, self.workname,
                         self.constraints, self.attempt))
        cursor.execute('commit;')

    def log(self, cursor, l):
        timestamp = datetime.datetime.now()
        print '%s %s' % (timestamp, l.rstrip())
        self.batchlog(cursor, [(timestamp, l)])

    def batchlog(self, cursor, entries):
        logdir = os.path.join('/srv/logs', self.ident)
        if not os.path.exists(logdir):
           os.makedirs(logdir)

        logpath = os.path.join(logdir,
                               (str(self.number) +
                                (utils.format_attempt_path(self.attempt) +
                                 '_' + self.workname + '.log')))

        with open(logpath, 'a+') as f:
            sql = ('insert into work_logs(id, number, workname, worker, log, '
                   'timestamp, constraints, attempt) values ')
            values = []
            for timestamp, log in entries:
                values.append('("%s", %s, "%s", "%s", "%s", %s, "%s", %s)'
                              %(self.ident, self.number, self.workname,
                                self.worker, _mysql.escape_string(log),
                                utils.datetime_as_sql(timestamp),
                                self.constraints, self.attempt))
            f.write('%s %s\n' %(timestamp, log.rstrip()))

        sql += ', '.join(values)
        sql += ';'

        cursor.execute(sql)
        cursor.execute('commit;')

        if len(entries) > 1:
            print '%s Pushed %d log lines to server' %(datetime.datetime.now(),
                                                       len(entries))
        self.heartbeat(cursor)

    # Valid work done statuses:
    #    y = work done
    #    m = plugin not found
    #    c = git conflict during checkout

    def set_conflict(self, cursor):
        self.set_state(cursor, 'c')

    def set_done(self, cursor):
        self.set_state(cursor, 'y')
        print 'Marked %s %s %s %s(%s) done' %(self.ident, self.number,
                                              self.workname, self.constraints,
                                              self.attempt)

    def set_missing(self, cursor):
        self.set_state(cursor, 'm')

    def set_state(self, cursor, state):
        cursor.execute('update work_queue set done="%s" '
                       'where id="%s" and number=%s and workname="%s" '
                       'and constraints="%s" and attempt=%s;'
                       %(state, self.ident, self.number, self.workname,
                         self.constraints, self.attempt))
        cursor.execute('commit;')

    def record_migration(self, cursor, migration, name):
        cursor.execute('insert ignore into patchset_migrations'
                       '(id, number, migration, name) '
                       'values("%s", %s, %s, "%s");'
                       %(self.ident, self.number, migration, name))
        cursor.execute('commit;')

    def _unique_path(self):
        path = os.path.join(self.ident, str(self.number), self.workname)
        if self.constraints != 'mysql':
            path += '_%s' % self.constraints
        path += utils.format_attempt_path(self.attempt)
        return path

    def disk_path(self):
        return os.path.join('/var/www/ci', self._unique_path())

    def url(self):
        return os.path.join('http://openstack.stillhq.com',
                            self._unique_path())

    def persist_to_disk(self, cursor):
        cursor.execute('select * from work_queue where id="%s" and number=%s '
                       'and workname="%s" and constraints="%s" and '
                       'attempt=%s;'
                       %(self.ident, self.number, self.workname,
                         self.constraints, self.attempt))
        row = cursor.fetchone()
        if row['dumped'] == 'y':
            return

        subcursor = utils.get_cursor()

        path = self.disk_path()
        datapath = os.path.join(path, 'data')
        workerpath = os.path.join(path, 'worker')

        print path
        if not os.path.exists(path):
            os.makedirs(path)
        with open(workerpath, 'w') as f:
            f.write(self.worker)
        with open(os.path.join(path, 'log.html'), 'w') as f:
            buffered = []
            upgrades = []
            upgrade_times = {}
            in_upgrade = False
            migration_start = None
            final_version = None

            cursor.execute('select * from work_logs where id="%s" and '
                           'number=%s and workname="%s" and '
                           'worker="%s" and constraints="%s" and attempt=%s '
                           'order by timestamp asc;'
                           %(self.ident, self.number, self.workname,
                             self.worker, self.constraints, self.attempt))
            linecount = 0
            f.write(LOG_HEADER %{'id': self.ident,
                                 'number': self.number})

            data = {}
            for logrow in cursor:
                m = FINAL_VERSION_RE.match(logrow['log'])
                if m:
                    final_version = int(m.group(1))

                m = UPGRADE_BEGIN_RE.match(logrow['log'])
                if m:
                    upgrade_name = m.group(1)
                    upgrades.append(upgrade_name)
                    upgrade_start = logrow['timestamp']
                    in_upgrade = True

                    buffered.append('<a name="%s"></a>' % upgrade_name)

                m = MIGRATION_CLASH_RE.match(logrow['log'])
                if m:
                    data['color'] = 'bgcolor="#FA5858"'
                    data['result'] = 'Failed: migration number clash'
                    print '    Failed'

                line = ('<a name="%(linenum)s"></a>'
                        '<a href="#%(linenum)s">#</a> '
                        % {'linenum': linecount})
                if in_upgrade:
                    line += '<b>'

                cleaned = logrow['log'].rstrip()
                cleaned = cleaned.replace('/srv/openstack-ci-tools', '...')
                cleaned = GIT_CHECKOUT_RE.sub('...git...', cleaned)
                cleaned = VENV_PATH_RE.sub('...venv...', cleaned)
                cleaned = cgi.escape(cleaned)

                m = MIGRATION_END_RE.match(cleaned)
                if m and migration_start:
                    elapsed = logrow['timestamp'] - migration_start
                    cleaned += ('              <font color="red">[%s]</font>'
                                % utils.timedelta_as_str(elapsed))
                    migration_start = None

                m = MIGRATION_START_RE.match(cleaned)
                if m:
                    migration_start = logrow['timestamp']
                    subcursor.execute('select * from patchset_migrations '
                                      'where id="%s" and number=%s and '
                                      'migration=%s;'
                                      %(self.ident, self.number, m.group(2)))
                    subrow = subcursor.fetchone()
                    if subrow:
                        cleaned += ('     <font color="red">[%s]</font>'
                                    % subrow['name'])

                line += ('%(timestamp)s %(line)s'
                         % {'timestamp': logrow['timestamp'],
                            'line': cleaned})
                if in_upgrade:
                    line += '</b>'
                line += '\n'
                buffered.append(line)

                linecount += 1

                m = UPGRADE_END_RE.match(logrow['log'])
                if m:
                    in_upgrade = False
                    elapsed = logrow['timestamp'] - upgrade_start
                    elapsed_str = utils.timedelta_as_str(elapsed)
                    buffered.append('                                   '
                                    '     <font color="red"><b>'
                                    '[%s total]</b></font>\n'
                                    % elapsed_str)
                    upgrade_times[upgrade_name] = elapsed

            display_upgrades = []
            data.update({'order': upgrades,
                         'details' : {},
                         'details_seconds': {},
                         'final_schema_version': final_version})
            for upgrade in upgrades:
                time_str = utils.timedelta_as_str(upgrade_times[upgrade])
                display_upgrades.append('<li><a href="#%(name)s">'
                                        'Upgrade to %(name)s -- '
                                        '%(elapsed)s</a>'
                                        % {'name': upgrade,
                                           'elapsed': time_str})
                data['details'][upgrade] = time_str
                data['details_seconds'][upgrade] = \
                  upgrade_times[upgrade].seconds
                data['color'] = ''

                print '    %s (%s)' %(upgrade,
                                      upgrade_times[upgrade].seconds)
                if upgrade == 'patchset':
                    if upgrade_times[upgrade].seconds > 30:
                        data['color'] = 'bgcolor="#FA5858"'
                        data['result'] = 'Failed: patchset too slow'
                        print '        Failed'

            if final_version:
                subcursor.execute('select max(migration) from '
                                  'patchset_migrations where id="%s" '
                                  'and number=%s;'
                                  %(self.ident, self.number))
                subrow = subcursor.fetchone()
                data['expected_final_schema_version'] = \
                  subrow['max(migration)']
                if final_version != subrow['max(migration)']:
                    data['color'] = 'bgcolor="#FA5858"'
                    data['result'] = 'Failed: incorrect final version'
                    print '        Failed'

            f.write('<ul>%s</ul>' % ('\n'.join(display_upgrades)))
            f.write('<pre><code>\n')
            f.write(''.join(buffered))
            f.write('</code></pre></body></html>')

            with open(datapath, 'w') as d:
                d.write(json.dumps(data))
