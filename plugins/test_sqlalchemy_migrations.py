#!/usr/bin/python

import os
import re

import workunit
import utils


NEW_PATCH_EMAIL = """New database migration patchset discovered!

%(subject)s by %(name)s
%(url)s

%(change_id)s number %(number)s

The following files are changed in the patchset:
    %(files_list)s"""


def Handle(change, files):
    is_migration = False

    for filename in files:
        if filename.find('nova/db/sqlalchemy/migrate_repo/versions') != -1:
            is_migration = True

    if is_migration:
        print 'Sending email'
        utils.send_email('[CI] Patchset %s #%s' %(change['id'],
                                                  change['number']),
                         'michael.still@rackspace.com',
                         NEW_PATCH_EMAIL
                         % {'change_id': change['id'],
                            'number': change['number'],
                            'subject': change['subject'],
                            'name': change['owner_name'],
                            'url': change['url'],
                            'is_migration': is_migration,
                            'files_list': '\n    '.join(files)})

        cursor = utils.get_cursor()
        for dataset in ['nova_trivial_500', 'nova_trivial_6000',
                        'nova_user_001']:
            for constraint in ['mysql']:
                w = workunit.WorkUnit(change['id'], change['number'],
                                      'sqlalchemy_migration_%s' % dataset,
                                      0, constraint)
                w.enqueue_work(cursor)


MIGRATION_NAME_RE = re.compile('([0-9]+)_(.*)\.py')


def ExecuteWork(cursor, work, git_repo, change):
    if not work.workname.startswith('sqlalchemy_migration_'):
        return False

    work.log(cursor, 'Plugin for work queue item found.')

    # Record the migration names present
    version = {}
    migrations = os.path.join(git_repo,
                              'nova/db/sqlalchemy/migrate_repo/versions')
    for ent in os.listdir(migrations):
        m = MIGRATION_NAME_RE.match(ent)
        if m:
            work.record_migration(m.group(1), m.group(2))
            version.setdefault(m.group(1), [])
            version[m.group(1)].append(m.group(2))
    cursor.execute('commit;')

    # Make sure we only have one .py per version number
    for migration in version:
        if len(version[migration]) > 1:
            work.log(cursor,
                     'Error: migration number %s appears more than once'
                      % migration)
            for name in version[migration]:
                work.log(cursor, '%s: %s' %(migration, name))
            return True

    safe_refurl = change['refurl'].replace('/', '_')

    flags = utils.get_config()
    db = workname[len('sqlalchemy_migration_'):]
    cmd = ('/srv/openstack-ci-tools/plugins/test_sqlalchemy_migrations.sh '
           '%(ref_url)s %(git_repo)s %(dbuser)s %(dbpassword)s %(db)s'
           % {'ref_url': safe_refurl,
              'git_repo': git_repo,
              'dbuser': flags['test_dbuser'],
              'dbpassword': flags['test_dbpassword'],
              'db': db})
    utils.execute(cursor, work, cmd, timeout=(3600 * 2))
    return True
