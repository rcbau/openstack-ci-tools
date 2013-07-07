#!/usr/bin/python

"""Representation of a unit of work."""

# All code for the work_queue and work_logs tables should reside here.


import datetime
import os
import uuid

import utils


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
                 attempt=row['attempt'], constraints=row['constraints'])
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

    cursor.execute('insert into work_queue(id, number, workname, attempt) '
                   'values ("%s", %s, "%s", %s);'
                   %(ident, number, workname, attempt))
    cursor.execute('commit;')
    print 'Added recheck for %s %s %s' %(ident, number, workname)


class WorkUnit(object):
    def __init__(self, ident, number, attempt, constraints):
        self.ident = ident
        self.number = number
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
                       'worker="%s" and attempt=%s;'
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
        batchlog(cursor, [(timestamp, l)])

    def batchlog(self, cursor, entries):
        logdir = os.path.join('/srv/logs', ident)
        if not os.path.exists(logdir):
           os.makedirs(logdir)

        logpath = os.path.join(logdir,
                               (str(self.number) +
                                (utils.format_attempt_path(self.attempt) +
                                 '_' + workname + '.log')))

        with open(logpath, 'a+') as f:
            sql = ('insert into work_logs(id, number, workname, worker, log, '
                   'timestamp, constraints, attempt) values ')
            values = []
            for timestamp, log in entries:
                values.append('("%s", %s, "%s", "%s", "%s", %s, "%s", %s)'
                              %(self.ident, self.number, self.workname,
                                self.worker, _mysql.escape_string(log),
                                utils.datetime_as_sql(timestamp),
                                self.contstraints, self.attempt))
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
