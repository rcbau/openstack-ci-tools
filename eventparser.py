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
FETCH_DAYS = 3


# Valid states:
#   0: not fetched
#   m: fetch skipped as git repo missing
#   f: fetched and converted into a list of changed files
#   p: plugins run


rechecks = {}


def fetch_log_day(dt):
    global rechecks

    new = 0
    cursor = utils.get_cursor()

    for host in ['dfw', 'ord', 'syd']:
        try:
            print ('%s Fetching http://gerrit-stream-logger-%s.stillhq.com/'
                   'output/%s/%s/%s'
                   %(datetime.datetime.now(),
                     host, dt.year, dt.month, dt.day))
            remote = urllib.urlopen('http://gerrit-stream-logger-%s.'
                                    'stillhq.com/output/%s/%s/%s'
                                    %(host, dt.year, dt.month, dt.day))
            for line in remote.readlines():
                packet = json.loads(line)
                if packet.get('type') == 'patchset-created':
                    ts = packet['patchSet']['createdOn']
                    ts = datetime.datetime.fromtimestamp(ts)
                    cursor.execute('insert ignore into patchsets '
                                   '(id, project, number, refurl, state, '
                                   'subject, owner_name, url, timestamp) '
                                   'values (%s, %s, %s, %s, 0, %s, %s, %s, '
                                   '%s);',
                                   (packet['change']['id'],
                                    packet['change']['project'],
                                    packet['patchSet']['number'],
                                    packet['patchSet']['ref'],
                                    utils.Normalize(
                                        packet['change']['subject']),
                                    utils.Normalize(
                                        packet['change']['owner']['name']),
                                    packet['change']['url'],
                                    ts))
                    new += cursor.rowcount
                    cursor.execute('update patchsets set timestamp=%s where '
                                   'id=%s and number=%s;',
                                   (ts,
                                    packet['change']['id'],
                                    packet['patchSet']['number']))
                    cursor.execute('commit;')

                elif packet.get('type') == 'comment-added':
                    if (packet.get('comment').startswith('recheck') or
                        packet.get('comment').startswith('reverify')):
                        # Confusingly, this is the timestamp for the comment
                        ts = packet['patchSet']['createdOn']
                        ts = datetime.datetime.fromtimestamp(ts)
                        key = (packet['change']['id'],
                               packet['patchSet']['number'])
                        rechecks.setdefault(key, [])
                        if not ts in rechecks[key]:
                            rechecks[key].append(ts)

        except Exception, e:
            print '%s Error: %s' %(datetime.datetime.now(), e)

        try:
            process_patchsets()
            perform_git_fetches()
            process_patchsets()
        except Exception, e:
            print '%s Error %s' %(datetime.datetime.now(), e)

    return new


def perform_git_fetches():
    fetches_performed = False
    cursor = utils.get_cursor()
    subcursor = utils.get_cursor()
    cursor.execute('select * from patchsets where state="0" limit 25;')

    for row in cursor:
        fetches_performed = True
        repo_path = os.path.join('/srv/git', row['project'])
        if not os.path.exists(repo_path):
            utils.clone_git(row['project'])

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
        print '%s %s' %(datetime.datetime.now(), row['refurl'])
        repo.git.fetch('https://review.openstack.org/%s' %row['project'],
                       row['refurl'])
        for line in repo.git.format_patch('-1', '--stdout',
                                          'FETCH_HEAD').split('\n'):
            m = DIFF_FILENAME_RE.match(line)
            if m:
                files[m.group(1)] = True
        print '%s  %d files changed' %(datetime.datetime.now(), len(files))

        for filename in files:
            subcursor.execute('insert ignore into patchset_files '
                              '(id, number, filename) values ("%s", %d, "%s");'
                              %(row['id'], row['number'], filename))
        subcursor.execute('update patchsets set state="f" '
                          'where id="%s" and number=%d;'
                          %(row['id'], row['number']))
        subcursor.execute('commit;')

    return fetches_performed


def process_patchsets():
    cursor = utils.get_cursor()

    # Load plugins
    plugins = []
    for ent in os.listdir('plugins'):
        if ent[0] != '.' and ent.endswith('.py'):
            plugin_info = imp.find_module(ent[:-3], ['plugins'])
            plugins.append(imp.load_module(ent[:-3], *plugin_info))

    cursor.execute('select * from patchsets where state="f";')
    subcursor = utils.get_cursor()

    for row in cursor:
        age = datetime.datetime.now() - row['timestamp']
        if age.days < 2:
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
    now = datetime.datetime.now()
    new = 0

    for i in range(FETCH_DAYS):
        try:
            new += fetch_log_day(now)
        except Exception, e:
            print e

        now -= datetime.timedelta(days=1)

    print '%s Added %d new patchsets' %(datetime.datetime.now(), new)

    while perform_git_fetches():
        process_patchsets()
    process_patchsets()

    cursor = utils.get_cursor()
    for ident, number in rechecks:
        for ts in rechecks[(ident, number)]:
            cursor.execute('insert ignore into patchset_rechecks '
                           '(id, number, timestamp) values ("%s", %s, %s);'
                           %(ident, number, utils.datetime_as_sql(ts)))
            if cursor.rowcount:
                delta = datetime.datetime.now() - ts
                if delta.days > 3:
                    print 'Recheck ignored because it is older than three days'
                else:
                    print 'Recheck'
                    utils.recheck(ident, number)
            cursor.execute('commit;')
