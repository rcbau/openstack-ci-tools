#!/usr/bin/python

import json
import MySQLdb

def GetCursor():
    # Read config from a file
    with open('/srv/config/gerritevents') as f:
        flags = json.loads(f.read())

    db = MySQLdb.connect(user = flags['dbuser'],
                         db = flags['dbname'],
                         passwd = flags['dbpassword'])
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    return cursor
