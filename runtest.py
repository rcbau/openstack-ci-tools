#!/usr/bin/python

import datetime
import os
import select
import socket
import subprocess
import time
import utils


cursor = utils.get_cursor()
cmd = ('./plugins/test_sqlalchemy_migrations.sh refs_changes_51_29251_11 '
       '/srv/git-checkouts/testing nova nova nova_user_001 2>&1')

for i in range(0, 5):
    print 'Executing script: %s' % cmd

    names = {}
    lines = {}
    syslog = os.open('/var/log/syslog', os.O_RDONLY)
    os.lseek(syslog, 0, os.SEEK_END)
    names[syslog] = '[syslog] '
    lines[syslog] = ''

    slow = os.open('/var/log/mysql/slow-queries.log', os.O_RDONLY)
    os.lseek(slow, 0, os.SEEK_END)
    names[slow] = '[mysql slow queries] '
    lines[slow] = ''

    mysql = os.open('/var/log/mysql/error.log', os.O_RDONLY)
    os.lseek(mysql, 0, os.SEEK_END)
    names[mysql] = '[mysql error] '
    lines[mysql] = ''

    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    names[p.stdout.fileno()] = ''
    lines[p.stdout.fileno()] = ''

    poll_obj = select.poll()
    poll_obj.register(p.stdout, select.POLLIN)
    poll_obj.register(syslog, select.POLLIN)
    poll_obj.register(slow, select.POLLIN)
    poll_obj.register(mysql, select.POLLIN)

    log = []
    last_heartbeat = time.time()
    while p.poll() is None:
        for fd, _ in poll_obj.poll(0):
            lines[fd] += os.read(fd, 1024)
            if lines[fd].find('\n') != -1:
                elems = lines[fd].split('\n')
                for l in elems[:-1]:
                    l = '%s%s' %(names[fd], l)
                    log.append((datetime.datetime.now(), l))
                    print '%s %s' %(datetime.datetime.now(), l.rstrip())
                lines[fd] = elems[-1]
                last_heartbeat = time.time()

        if time.time() - last_heartbeat > 30:
            log.append((datetime.datetime.now(), '[heartbeat]'))
            print '%s [heartbeat]' % datetime.datetime.now()
            last_heartbeat = time.time()

    for fd in lines:
        if lines[fd]:
            l = '%s%s' %(names[fd], l)
            log.append((datetime.datetime.now(), l))
            print '%s %s' %(datetime.datetime.now(), l.rstrip())

    utils.batchlog(cursor, socket.gethostname(), 'performance', i + 1,
                   'nova_user_001', log)
    time.sleep(900)
