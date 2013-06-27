#!/usr/bin/python

# Args are:
#  change id
#  number
#  workname

import sys
import utils


cursor = utils.get_cursor()
cursor.execute('select max(attempt) from work_queue where id="%s" and number=%s and workname="%s";'
               %(sys.argv[1], sys.argv[2], sys.argv[3]))
row = cursor.fetchone()
attempt = row['max(attempt)']

print 'Previous attempt was %s' % attempt
attempt += 1

cursor.execute('insert into work_queue(id, number, workname, attempt) values ("%s", %s, "%s", %s);'
               %(sys.argv[1], sys.argv[2], sys.argv[3], attempt))
cursor.execute('commit;')
