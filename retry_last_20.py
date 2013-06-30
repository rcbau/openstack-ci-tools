#!/usr/bin/python

# Recheck the last 20 reviews

import sys
import utils


cursor = utils.get_cursor()
cursor.execute('select distinct(concat(id, "~", number)) as idnum from work_queue order by heartbeat desc limit 20;')
for row in cursor:
    id, number = row['idnum'].split('~')
    utils.recheck(id, int(number))
