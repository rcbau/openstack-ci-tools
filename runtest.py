#!/usr/bin/python

import datetime
import socket
import subprocess
import time
import utils


cursor = utils.get_cursor()
cmd = './plugins/test_sqlalchemy_migrations.sh refs_changes_51_29251_11 /srv/git-checkouts/testing nova nova nova_user_001 2>&1'

for i in range(0, 5):
    print 'Executing script: %s' % cmd
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)

    log = []
    l = p.stdout.readline()
    while l:
        l = p.stdout.readline()
        log.append((datetime.datetime.now(), l))
        print '%s %s' %(datetime.datetime.now(), l.rstrip())

    utils.batchlog(cursor, socket.gethostname(), 'performance', i + 1, 'nova_user_001', log)
    time.sleep(900)
