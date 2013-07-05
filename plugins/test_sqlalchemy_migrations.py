#!/usr/bin/python

import os
import re

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
            utils.queue_work(cursor, change['id'], change['number'],
                             'sqlalchemy_migration_%s' % dataset)


MIGRATION_NAME_RE = re.compile('([0-9]+)_(.*)\.py')


def ExecuteWork(cursor, ident, number, workname, worker, attempt, git_repo,
                change):
    if not workname.startswith('sqlalchemy_migration_'):
        return False

    utils.log(cursor, worker, ident, number, workname, attempt,
              'Plugin for work queue item found.')

    # Record the migration names present
    version = {}
    migrations = os.path.join(git_repo,
                              'nova/db/sqlalchemy/migrate_repo/versions')
    for ent in os.listdir(migrations):
        m = MIGRATION_NAME_RE.match(ent)
        if m:
            cursor.execute('insert ignore into patchset_migrations'
                           '(id, number, migration, name) '
                           'values("%s", %s, %s, "%s");'
                           %(ident, number, m.group(1), m.group(2)))
            version.setdefault(number, [])
            version[number].append(name)
    cursor.execute('commit;')

    # Make sure we only have one .py per version number
    for number in version:
        if len(version[number]) > 1:
            utils.log(cursor, worker, ident, number, workname, attempt,
                      'Error: migration number %s appears more than once'
                      % number)
            for name in version[number]:
                utils.log(cursor, worker, ident, number, workname, attempt,
                          '%s: %s' %(number, name))
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
    utils.execute(cursor, worker, ident, number, workname, attempt, cmd,
                  timeout=(3600 * 2))
    return True
