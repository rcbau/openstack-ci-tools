#!/usr/bin/python


import git
import json
import mimetypes
import MySQLdb
import os
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
        return json.loads(f.read().replace('\n', ''))


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


def create_git(project, refurl):
    """Get a safe COW git checkout of the named refurl."""

    git_dir, cow_dir, visible_dir = _calculate_directories(project, refurl)
    if not os.path.exists(cow_dir):
        os.makedirs(cow_dir)
    if not os.path.exists(visible_dir):
        os.makedirs(visible_dir)
    cmd = ('sudo unionfs-fuse -o cow,max_files=32768 '
           '-o allow_other,use_ino,suid,dev,nonempty '
           '%(cow_dir)s=rw:%(git_dir)s=ro %(visible_dir)s'
           %{'cow_dir': cow_dir,
             'git_dir': git_dir,
             'visible_dir': visible_dir})
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    print 'Mount stdout: %s' % p.stdout.readlines()

    repo = git.Repo(os.path.join(GIT_DIR, project))
    assert repo.bare == False
    repo.git.checkout('master')
    repo.git.pull()

    repo = git.Repo(visible_dir)
    assert repo.bare == False
    repo.git.fetch('https://review.openstack.org/%s' % project, refurl)
    repo.git.checkout('FETCH_HEAD')
    repo.git.checkout('-b', 'target')
    repo.git.commit('-a', '-m', 'Commit target')

    return visible_dir


def release_git(project, refurl):
    """Destroy a git checkout."""

    git_dir, cow_dir, visible_dir = _calculate_directories(project, refurl)
    cmd = ('sudo umount %(visible_dir)s' % {'visible_dir': visible_dir})
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    print 'Unmount stdout: %s' % p.stdout.readlines()


def queue_work(cursor, ident, number, workname):
    cursor.execute('insert ignore into work_queue(id, number, workname) values '
                   '("%s", %d, "%s");'
                   %(ident, number, workname))
    cursor.execute('commit;')


def dequeue_work(cursor, worker):
    selectid = str(uuid.uuid4())
    cursor.execute('update work_queue set selectid="%s", worker="%s", '
                   'heartbeat = NOW() where selectid is NULL limit 1;'
                   %(selectid, worker))
    cursor.execute('commit;')
    cursor.execute('select * from work_queue where selectid="%s";'
                   % selectid)
    row = cursor.fetchone()
    return (row['id'], row['number'], row['workname'])


def log(cursor, worker, ident, number, workname, log):
    cursor.execute('insert into work_logs(id, number, workname, worker, log, '
                   'timestamp) values(%s, %s, %s, %s, %s, now());',
                   (ident, number, workname, worker, log))
    heartbeat(cursor, worker, ident, number, workname)


def heartbeat(cursor, worker, ident, number, workname):
    cursor.execute('update work_queue set heartbeat=NOW() where '
                   'id="%s" and number=%s and workname="%s" and '
                   'worker="%s";'
                   %(ident, number, workname, worker))
    cursor.execute('commit;')
