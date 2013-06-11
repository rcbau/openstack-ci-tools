#!/usr/bin/python

import datetime
import git
import json
import mimetypes
import MySQLdb
import os
import shutil
import smtplib
import subprocess
import uuid

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def get_config():
    # Read config from a file
    with open('/srv/config/gerritevents') as f:
        config = f.read().replace('\n', '')
        return json.loads(config)


def get_cursor():
    """Get a database cursor."""
    flags = get_config()
    db = MySQLdb.connect(user = flags['dbuser'],
                         db = flags['dbname'],
                         passwd = flags['dbpassword'],
                         host = flags['dbhost'])
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    return cursor


def send_email(subject, mailto, body):
    """Send an email."""

    with open('/srv/config/gerritevents') as f:
        flags = json.loads(f.read())

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = flags['mailfrom']
    msg['To'] = mailto

    msg.preamble = body
    txt = MIMEText(body, 'plain')
    msg.attach(txt)

    s = smtplib.SMTP(flags['mailserver'])
    s.sendmail(flags['mailfrom'], [mailto], msg.as_string())
    s.quit()


GIT_DIR = '/srv/git'
COW_DIR = '/srv/git-shadow'
VISIBLE_DIR = '/srv/git-checkouts'


def get_patchset_details(cursor, ident, number):
    cursor.execute('select * from patchsets where id="%s" and number=%s;'
                   %(ident, number))
    return cursor.fetchone()


def _calculate_directories(project, refurl):
    safe_refurl = refurl.replace('/', '_')
    git_dir = os.path.join(GIT_DIR, project)
    cow_dir = os.path.join(COW_DIR, project + '_' + safe_refurl)
    visible_dir = os.path.join(VISIBLE_DIR, project + '_' + safe_refurl)
    return (git_dir, cow_dir, visible_dir)


def create_git(project, refurl, cursor, worker, ident, number, workname, rewind):
    """Get a safe COW git checkout of the named refurl."""

    conflict = False
    git_dir, cow_dir, visible_dir = _calculate_directories(project, refurl)
    cmd = ('/srv/openstack-ci-tools/gitcheckout.sh "%(visible_dir)s" "%(project)s" "%(refurl)s" %(rewind)s 2>&1'
           %{'cow_dir': cow_dir,
             'git_dir': git_dir,
             'visible_dir': visible_dir,
             'project': project,
             'refurl': refurl,
             'rewind': rewind})
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    l = p.stdout.readline()
    while l:
        log(cursor, worker, ident, number, workname, l)
        if l.find('CONFLICT') != -1:
            conflict = True
        l = p.stdout.readline()
    return visible_dir, conflict


def queue_work(cursor, ident, number, workname):
    cursor.execute('insert ignore into work_queue(id, number, workname) values '
                   '("%s", %d, "%s");'
                   %(ident, number, workname))
    cursor.execute('commit;')


class NoWorkFound(Exception):
    pass


def dequeue_work(cursor, worker):
    selectid = str(uuid.uuid4())
    cursor.execute('update work_queue set selectid="%s", worker="%s", '
                   'heartbeat = NOW() where selectid is NULL limit 1;'
                   %(selectid, worker))
    cursor.execute('commit;')
    cursor.execute('select * from work_queue where selectid="%s";'
                   % selectid)
    if cursor.rowcount == 0:
        raise NoWorkFound()
    row = cursor.fetchone()
    return (row['id'], row['number'], row['workname'])


def clear_log(cursor, ident, number, workname):
    cursor.execute('delete from work_logs where id="%s" and number=%s and '
                   'workname="%s";'
                   %(ident, number, workname))
    cursor.execute('commit;')


def log(cursor, worker, ident, number, workname, log):
    print '%s %s' % (datetime.datetime.now(), log.rstrip())
    cursor.execute('insert into work_logs(id, number, workname, worker, log, '
                   'timestamp) values(%s, %s, %s, %s, %s, now());',
                   (ident, number, workname, worker, log))
    cursor.execute('commit;')
    heartbeat(cursor, worker, ident, number, workname)


def heartbeat(cursor, worker, ident, number, workname):
    cursor.execute('update work_queue set heartbeat=NOW() where '
                   'id="%s" and number=%s and workname="%s" and '
                   'worker="%s";'
                   %(ident, number, workname, worker))
    cursor.execute('commit;')
