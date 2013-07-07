#!/usr/bin/python

# Dump logs of jobs to a web server

import cgi
import datetime
import json
import os
import re

import utils
import workunit


NEW_RESULT_EMAIL = """Results for a test are available.

    %(results)s

"""


def test_name_as_display(test):
    return test.replace('sqlalchemy_migration_nova', 'nova upgrade').\
                replace('_', ' ')


def write_index(sql, filename):
    # Write out an index file
    order = []
    test_names = []
    cursor.execute(sql)
    for row in cursor:
        key = (row['id'], row['number'])

        if not key in order:
            order.append(key)
        if not row['workname'] in test_names:
            test_names.append(row['workname'])

    with open(filename, 'w') as f:
        cursor.execute('select count(*) from patchsets;')
        total = cursor.fetchone()['count(*)']
        cursor.execute('select count(*) from patchset_rechecks;')
        rechecks = cursor.fetchone()['count(*)']

        cursor.execute('select timestamp from patchsets order by '
                       'timestamp desc limit 1;')
        recent = cursor.fetchone()['timestamp']
        cursor.execute('select count(*) from work_queue where done="y";')
        jobs_done = cursor.fetchone()['count(*)']
        cursor.execute('select count(*) from work_queue where done is null;')
        jobs_queued = cursor.fetchone()['count(*)']

        f.write('<html><head><title>Recent tests</title></head><body>\n'
                '<p>This page lists recent CI tests run by this system.</p>\n'
                '<p>There are currently %(total)s patchsets tracked and '
                '%(retries)s rechecks, with %(jobs_done)s jobs having been '
                'run. There are %(jobs_queued)s jobs queued to run. The most '
                'recent patchset is from %(recent)s. This page was last '
                'updated at %(now)s.</p>'
                '<table><tr><td><b>Patchset</b></td>'
                %{'total': total,
                  'retries': rechecks,
                  'jobs_done': jobs_done,
                  'jobs_queued': jobs_queued,
                  'recent': recent,
                  'now': datetime.datetime.now()})

        test_names.sort()
        for test in test_names:
            f.write('<td><b>%s</b></td>' % test_name_as_display(test))
        f.write('</tr>\n')

        row_colors = ['', ' bgcolor="#CCCCCC"']
        row_count = 0
        for key in order:
            cursor.execute('select * from patchsets where id="%s" and '
                           'number=%s order by timestamp desc limit 1;'
                           %(key[0], key[1]))
            row = cursor.fetchone()
            f.write('<tr%(color)s><td>'
                    '<a href="%(id)s/%(num)s">%(id)s #%(num)s</a><br/>'
                    '<font size="-1">%(proj)s at %(timestamp)s<br/>'
                    '<a href="%(url)s">%(subj)s by %(who)s</a><br/>'
                    '</font></td>'
                    % {'color': row_colors[row_count % 2],
                       'id': key[0],
                       'num': key[1],
                       'proj': row['project'],
                       'timestamp': row['timestamp'],
                       'subj': row['subject'],
                       'who': row['owner_name'],
                       'url': row['url']})
            for test in test_names:
                f.write('<td><table>')
                for work in workunit.find_latest_attempts(cursor, key[0],
                                                          key[1], test):
                    test_dir = work.disk_path()
                    if os.path.exists(test_dir):
                        with open(os.path.join(test_dir, 'data'), 'r') as d:
                            data = json.loads(d.read())
                        color = data.get('color', '')
                        f.write('<tr %s><td><b>%s</b>'
                                '<a href="%s/log.html">log</a>'
                                '<font size="-1">'
                                %(color, work.constraints, work.url()))

                        if data.get('result', ''):
                            f.write('<br/><b>%s</b><br/>'
                                    % data.get('result', ''))

                        for upgrade in data['order']:
                            f.write('<br/>%s: %s' %(upgrade,
                                                    data['details'][upgrade]))

                        if data.get('final_schema_version', ''):
                            f.write('<br/>Final schema version: %s'
                                    % data.get('final_schema_version'))
                        if data.get('expected_final_schema_version', ''):
                            f.write('<br/>Expected schema version: %s'
                                    % data.get('expected_final_schema_version'))

                        cursor.execute('select * from work_queue where id="%s" '
                                       'and number=%s and workname="%s";'
                                       %(key[0], key[1], test))
                        row = cursor.fetchone()
                        f.write('<br/>Run at %s' % row['heartbeat'])

                        if work.attempt > 0:
                            f.write('<br/><br/>Other attempts: ')
                            for i in range(0, work.attempt):
                                f.write('<a href="%s/log.html">%s</a> '
                                        %(work.url(attempt=i)), i)

                        f.write('</font></td></tr>')
                    else:
                        f.write('<tr><td>&nbsp;</td></tr>')

            f.write('</table></td></tr>\n')
            row_count += 1
        f.write('</table></body></html>')


if __name__ == '__main__':
    print '...'

    cursor = utils.get_cursor()
    subcursor = utils.get_cursor()

    # Write out individual work logs
    cursor.execute('select * from work_queue where done is not null '
                   'and dumped is null;')
    for row in cursor:
        work = workunit.WorkUnit(row['id'], row['number'], row['workname'],
                                 row['attempt'], row['constraints'])
        work.worker = row['worker']
        work.persist_to_disk(subcursor)
        work.mark_dumped(subcursor)

    # Write out an index file
    write_index('select * from work_queue order by heartbeat desc limit 100;',
                '/var/www/ci/index.html')
    write_index('select * from work_queue order by heartbeat desc;',
                '/var/www/ci/all.html')

    # Email out results, but only if all tests complete
    candidates = {}
    cursor.execute('select * from work_queue where done is not null and '
                   'emailed is null;')
    for row in cursor:
        candidates[(row['id'], row['number'])] = True

    for ident, number in candidates:
        cursor.execute('select count(*) from work_queue where id="%s" and '
                       'number=%s and done is null;'
                       %(ident, number))
        row = cursor.fetchone()
        if row['count(*)'] > 0:
            print '%s #%s not complete' %(ident, number)
            continue

        # If we get here, then we owe people an email about a complete run of
        # tests
        results = {}
        cursor.execute('select * from work_queue where id="%s" and number=%s '
                       'and done is not null;'
                       %(ident, number))
        for row in cursor:
            work = workunit.WorkUnit(row['id'], row['number'], row['workname'],
                                     row['attempt'], row['constraints'])

            results.setdefault((row['workname'], row['constraints']), {})
            results[(row['workname'],
                     row['constraints'])].setdefault(row['attempt'], [])
            results[(row['workname'],
                     row['constraints'])][row['attempt']].append(
                          '%s attempt %s:'
                          %(test_name_as_display(row['workname']),
                            row['attempt']))
            with open(os.path.join(work.disk_path(), 'data')) as f:
                data = json.loads(f.read())

                if data.get('result', ''):
                    results[(row['workname'],
                             row['constraints'])][row['attempt']].append(
                                 '    %s' % data.get('result', ''))

                for upgrade in data['order']:
                    results[(row['workname'],
                             row['constraints'])][row['attempt']].append(
                                 '    %s: %s' %(upgrade,
                                                data['details'][upgrade]))

            results[(row['workname'],
                     row['constraints'])][row['attempt']].append(
                          '    Log URL: %s' % work.url())
            results[(row['workname'],
                     row['constraints'])][row['attempt']].append('')

        result = []
        for workname, constraint in sorted(results.keys()):
            attempt = max(results[(workname, constraint)].keys())
            for line in results[(workname, constraint)][attempt]:
                result.append(line)

        print 'Emailing %s #%s' %(ident, number)
        utils.send_email('Patchset %s #%s' %(ident, number),
                         'ci@lists.stillhq.com',
                         NEW_RESULT_EMAIL
                         % {'results': '\n'.join(result)})

        for workname, constraints in results:
            for attempt in results[(workname, constraints)]:
                subcursor.execute('update work_queue set emailed = "y" where '
                                  'id="%s" and number=%s and workname="%s" '
                                  'and constraints="%s" and attempt>=%s;'
                                  %(ident, number, workname, constraints,
                                    attempt))
        subcursor.execute('commit;')

    # Write a log of all migrations we have ever seen
    cursor.execute('select max(migration) from patchset_migrations;')
    max_migration = cursor.fetchone()['max(migration)']
    for i in range(max_migration - 10, max_migration + 1):
        with open(os.path.join('/var/www/ci/migrations/nova',
                               str(i) + '.html'),
                  'w') as f:
            sql = ('select distinct(id) from patchset_files '
                   'where filename like '
                   '"nova/db/sqlalchemy/migrate_repo/versions/%s_%%" '
                   'order by id;'
                   % i)
            cursor.execute(sql)
            counter = 1
            for row in cursor:
                f.write('<li><a href="http://review.openstack.org/#/q/%s,n,z">'
                        '%s</a>' %(row['id'], row['id']))
                counter += 1
            f.write('<br/><br/>%d patchsets' %(counter - 1))
