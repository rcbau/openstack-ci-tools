#!/usr/bin/python

import datetime
import git
import json
import mimetypes
import MySQLdb
import os
import select
import shutil
import smtplib
import subprocess
import sys
import time
import unicodedata

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


def format_attempt_path(attempt):
    if attempt is None or attempt == 0:
        return ''
    return '_%s' % attempt


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


def get_patchset_details(cursor, work):
    cursor.execute('select * from patchsets where id="%s" and number=%s;'
                   %(work.ident, work.number))
    return cursor.fetchone()


def _calculate_directories(project, refurl):
    safe_refurl = refurl.replace('/', '_')
    git_dir = os.path.join(GIT_DIR, project)
    cow_dir = os.path.join(COW_DIR, project + '_' + safe_refurl)
    visible_dir = os.path.join(VISIBLE_DIR, project + '_' + safe_refurl)
    return (git_dir, cow_dir, visible_dir)


def clone_git(project):
    """Clone a git repo master."""

    proj_elems = project.split('/')
    cmd = ('/srv/openstack-ci-tools/gitclone.sh %s %s'
           %(proj_elems[0], proj_elems[1]))
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    l = p.stdout.readline()
    while l:
        print '%s %s' %(datetime.datetime.now(), l)
        l = p.stdout.readline()


def create_git(project, refurl, cursor, work, rewind):
    """Get a safe COW git checkout of the named refurl."""

    conflict = False
    git_dir, cow_dir, visible_dir = _calculate_directories(project, refurl)
    cmd = ('/srv/openstack-ci-tools/gitcheckout.sh "%(visible_dir)s" '
           '"%(project)s" "%(refurl)s" %(rewind)s 2>&1'
           %{'cow_dir': cow_dir,
             'git_dir': git_dir,
             'visible_dir': visible_dir,
             'project': project,
             'refurl': refurl,
             'rewind': rewind})
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    l = p.stdout.readline()
    while l:
        work.log(cursor, l)
        if l.find('CONFLICT') != -1:
            conflict = True
        l = p.stdout.readline()
    return visible_dir, conflict


def datetime_as_sql(value):
    return ('STR_TO_DATE("%s", "%s")'
            %(value.strftime('%a, %d %b %Y %H:%M:%S'),
              '''%a, %d %b %Y %H:%i:%s'''))


def execute(cursor, work, cmd, timeout=-1):
    names = {}
    lines = {}
    syslog = os.open('/var/log/syslog', os.O_RDONLY)
    os.lseek(syslog, 0, os.SEEK_END)
    names[syslog] = '[syslog] '
    lines[syslog] = ''

    slow = os.open('/var/log/mysql/slow-queries.log', os.O_RDONLY)
    os.lseek(slow, 0, os.SEEK_END)
    names[slow] = '[sqlslo] '
    lines[slow] = ''

    mysql = os.open('/var/log/mysql/error.log', os.O_RDONLY)
    os.lseek(mysql, 0, os.SEEK_END)
    names[mysql] = '[sqlerr] '
    lines[mysql] = ''

    cmd += ' 2>&1'
    start_time = time.time()
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    names[p.stdout.fileno()] = ''
    lines[p.stdout.fileno()] = ''

    poll_obj = select.poll()
    poll_obj.register(p.stdout, select.POLLIN | select.POLLHUP)
    poll_obj.register(syslog, select.POLLIN)
    poll_obj.register(slow, select.POLLIN)
    poll_obj.register(mysql, select.POLLIN)

    last_heartbeat = time.time()
    def process(fd):
        lines[fd] += os.read(fd, 1024 * 1024)
        if lines[fd].find('\n') != -1:
            elems = lines[fd].split('\n')
            for l in elems[:-1]:
                l = '%s%s' %(names[fd], l)
                work.log(cursor, l)
            lines[fd] = elems[-1]
            last_heartbeat = time.time()

    phase = 0
    while phase < 2:
        if timeout > 0 and time.time() - start_time > timeout:
            work.log(cursor, '[timeout]')
            os.kill(p.pid, 9)

        for fd, flag in poll_obj.poll(0):
            process(fd)

        if time.time() - last_heartbeat > 30:
            work.log(cursor, '[heartbeat]')
            last_heartbeat = time.time()

        if p.poll() is not None:
            phase += 1
            print 'Phase advanced to %s' % phase

    process(p.stdout.fileno())

    for fd in lines:
        if lines[fd]:
            l = '%s%s' %(names[fd], lines[fd])
            work.log(cursor, l)

    work.log(cursor, '[script exit code = %d]' % p.returncode)


def Normalize(value):
  normalized = unicodedata.normalize('NFKD', unicode(value))
  normalized = normalized.encode('ascii', 'ignore')
  return normalized


def timedelta_as_str(delta):
    seconds = delta.days * (24 * 60 * 60)
    seconds += delta.seconds

    if seconds < 60:
        return '%d seconds' % seconds

    remainder = seconds % 60
    return '%d minutes, %d seconds' %((seconds - remainder) / 60,
                                      remainder)
