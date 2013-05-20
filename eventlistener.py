#!/usr/bin/python

# Listen to events from gerrit and log them to files. Run more than
# one of these, as a failure will cause a gap in the event stream.

import datetime
import os
import paramiko
import random
import sys
import time


hostname = 'review.openstack.org'
hostport = 29418
username = 'mikalstill'
keyfile = '/home/mikal/.ssh/id_gerrit'


def stream_events():
    last_event = time.time()
    wait_time = 300 + random.randint(0, 300)

    # Connect
    transport = paramiko.Transport((hostname, hostport))
    transport.start_client()

    # Authenticate with the key
    key = paramiko.RSAKey.from_private_key_file(keyfile)
    transport.auth_publickey(username, key)

    channel = transport.open_session()
    channel.exec_command('gerrit stream-events')

    print '%s Connected' % datetime.datetime.now()
    data = ''

    try:
        while True:
            if not channel.recv_ready():
                if time.time() - last_event > wait_time:
                    print ('%s Possibly stale connection'
                           % datetime.datetime.now())
                    return
                time.sleep(1)

            else:
                d = channel.recv(1024)
                if not d:
                    print '%s Connection closed' % datetime.datetime.now()
                    return

                last_event = time.time()
                print '%s Read %d bytes' %(datetime.datetime.now(), len(d))
                data += d

                if data.find('\n') != -1:
                    lines = data.split('\n')
                    for line in lines[:-1]:
                        now = datetime.datetime.now()
                        path = os.path.join('output', str(now.year),
                                            str(now.month))
                        if not os.path.exists(path):
                            os.makedirs(path)
                        with open(os.path.join(path, str(now.day)), 'a') as f:
                            f.write('%s\n' % line)

                    data = lines[-1]

    finally:
        transport.close()


if __name__ == '__main__':
    random.seed()
    while True:
        stream_events()
