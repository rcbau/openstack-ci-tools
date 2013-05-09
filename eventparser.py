#!/usr/bin/python

# Parse the logs written by the listener into events we want to run things on.
# These events are stored in a mysql database.

import datetime
import json
import MySQLdb
import urllib

import utils


def fetch_log_day(cursor, dt):
    new = 0

    for host in ['50.56.178.145', '198.61.229.73']:
        remote = urllib.urlopen('http://%s/output/%s/%s/%s'
                                %(host, dt.year, dt.month, dt.day))
        for line in remote.readlines():
            packet = json.loads(line)
            if packet.get('type') == 'patchset-created':
                cursor.execute('insert ignore into patchsets '
                               '(id, project, number, refurl, git_fetched) '
                               'values ("%s", "%s", %s, "%s", 0);'
                               %(packet['change']['id'],
                                 packet['change']['project'],
                                 packet['patchSet']['number'],
                                 packet['patchSet']['ref']))
                new += cursor.rowcount
                cursor.execute('commit;')

    return new


if __name__ == '__main__':
    cursor = utils.GetCursor()
    now = datetime.datetime.now()
    new = 0
    
    for i in range(7):
        try:
            new += fetch_log_day(cursor, now)
        except Exception, e:
            print e

        now -= datetime.timedelta(days=1)

    print 'Added %d new patchsets' % new
