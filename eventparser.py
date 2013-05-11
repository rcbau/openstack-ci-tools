#!/usr/bin/python

# Parse the logs written by the listener into events we want to run things on.
# These events are stored in a mysql database.

import datetime
import git
import imp
import json
import MySQLdb
import os
import re
import urllib

import utils


DIFF_FILENAME_RE = re.compile('^[\-\+][\-\+][\-\+] [ab]/(.*)$')


# Valid states:
#   0: not fetched
#   m: fetch skipped as git repo missing
#   f: fetched and converted into a list of changed files
#   p: plugins run


def fetch_log_day(cursor, dt):
    new = 0

    for host in ['50.56.178.145', '198.61.229.73']:
        remote = urllib.urlopen('http://%s/output/%s/%s/%s'
                                %(host, dt.year, dt.month, dt.day))
        for line in remote.readlines():
            packet = json.loads(line)
            if packet.get('type') == 'patchset-created':
                cursor.execute('insert ignore into patchsets '
                               '(id, project, number, refurl, state, subject, '
                               ' owner_name, url) '
                               'values (%s, %s, %s, %s, 0, %s, %s, %s);',
                               (packet['change']['id'],
                                packet['change']['project'],
                                packet['patchSet']['number'],
                                packet['patchSet']['ref'],
                                packet['change']['subject'],
                                packet['change']['owner']['name'],
                                packet['change']['url']))
                new += cursor.rowcount
                cursor.execute('commit;')

    return new


def perform_git_fetches(cursor):
    cursor.execute('select * from patchsets where state="0";')
    subcursor = utils.get_cursor()

    for row in cursor:
        repo_path = os.path.join('/srv/git', row['project'])
        if not os.path.exists(repo_path):
            subcursor.execute('update patchsets set state="m" '
                              'where id="%s" and number=%d;'
                              %(row['id'], row['number']))
            subcursor.execute('commit;')
            continue

        repo = git.Repo(repo_path)
        assert repo.bare == False
        repo.git.checkout('master')
        repo.git.pull()

        files = {}
        print row['refurl']
        repo.git.fetch('https://review.openstack.org/%s' %row['project'],
                       row['refurl'])
        for line in repo.git.format_patch('-1', '--stdout',
                                          'FETCH_HEAD').split('\n'):
            m = DIFF_FILENAME_RE.match(line)
            if m:
                files[m.group(1)] = True
        print '  %d files changed' % len(files)

        for filename in files:
            subcursor.execute('insert ignore into patchset_files '
                              '(id, number, filename) values ("%s", %d, "%s");'
                              %(row['id'], row['number'], filename))
        subcursor.execute('update patchsets set state="f" '
                          'where id="%s" and number=%d;'
                          %(row['id'], row['number']))
        subcursor.execute('commit;')


def process_patchsets(cursor):
    # Load plugins
    plugins = []
    for ent in os.listdir('plugins'):
        if ent[0] != '.' and ent.endswith('.py'):
            plugin_info = imp.find_module(ent[:-3], ['plugins'])
            plugins.append(imp.load_module(ent[:-3], *plugin_info))

    cursor.execute('select * from patchsets where state="f";')
    subcursor = utils.get_cursor()

    for row in cursor:
        files = []
        subcursor.execute('select * from patchset_files where id="%s" and '
                          'number=%d;'
                          %(row['id'], row['number']))
        for subrow in subcursor:
            files.append(subrow['filename'])

        for plugin in plugins:
            plugin.Handle(row, files)

        subcursor.execute('update patchsets set state="p" '
                          'where id="%s" and number=%d;'
                          %(row['id'], row['number']))
        subcursor.execute('commit;')


if __name__ == '__main__':
    cursor = utils.get_cursor()
    now = datetime.datetime.now()
    new = 0

    for i in range(7):
        try:
            new += fetch_log_day(cursor, now)
        except Exception, e:
            print e

        now -= datetime.timedelta(days=1)

    print 'Added %d new patchsets' % new
    perform_git_fetches(cursor)
    print 'Patchsets fetched'
    process_patchsets(cursor)
    print 'Plugin run complete'
