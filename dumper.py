#!/usr/bin/python

# Dump logs of jobs to a web server

import os

import utils

if __name__ == '__main__':
    cursor = utils.get_cursor()
    subcursor = utils.get_cursor()
    cursor.execute('select * from work_queue where done is not null;')
    for row in cursor:
        path = os.path.join('/var/www/ci', row['id'], str(row['number']), row['workname'])
        workerpath = os.path.join(path, 'worker')
        worker = None
        if os.path.exists(workerpath):
            with open(workerpath, 'r') as f:
                worker = f.read().rstrip()

        if worker != row['worker']:
            print path
            if not os.path.exists(path):
                os.makedirs(path)
            with open(workerpath, 'w') as f:
                f.write(row['worker'])
            with open(os.path.join(path, 'state'), 'w') as f:
                f.write(row['done'])
            with open(os.path.join(path, 'log'), 'w') as f:
                subcursor.execute('select * from work_logs where id="%s" and number=%s and workname="%s" and worker="%s" order by timestamp asc;'
                                  %(row['id'], row['number'], row['workname'], row['worker']))
                for logrow in subcursor:
                    f.write('%s %s\n' %(logrow['timestamp'], logrow['log'].rstrip()))
