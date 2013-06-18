#!/usr/bin/python

import datetime
import time

import utils


def wait_until_done():
    while True:
        cursor = utils.get_cursor()
        cursor.execute('select count(*) from patchsets where state = "0";')
        row = cursor.fetchone()
        print '%s %d rows' %(datetime.datetime.now(), row['count(*)'])
        if row['count(*)'] == 0:
            return
        time.sleep(30)


def process_all():
    while True:
        wait_until_done()
        cursor = utils.get_cursor()
        cursor.execute('update patchsets set state="0" where state="m" and project not like "stackforge/%reddwarf%" limit 100;')
        try:
            if cursor.rowcount == 0:
                return
        finally:
            cursor.execute('commit;')


process_all()
