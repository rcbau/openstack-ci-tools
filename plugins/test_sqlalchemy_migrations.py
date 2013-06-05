#!/usr/bin/python

import subprocess
import utils


NEW_PATCH_EMAIL = """The CI watcher has discovered a new patchset!

%(subject)s by %(name)s
%(url)s

%(change_id)s number %(number)s
is_migration: %(is_migration)s

The following files are changed in the patchset:
    %(files_list)s"""


def Handle(change, files):
    is_migration = False

    for filename in files:
        if filename.find('nova/db/sqlalchemy/migrate_repo/versions') != -1:
            is_migration = True

    if is_migration:
        print 'Sending email'
        utils.send_email('New patchset discovered!',
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
        for dataset in ['nova_trivial_500', 'nova_trivial_6000', 'nova_user_001']:
            utils.queue_work(cursor, change['id'], change['number'],
                             'sqlalchemy_migration_%s' % dataset)


def ExecuteWork(cursor, ident, number, workname, worker):
    if notworkname.startswith('sqlalchemy_migration_'):
        return False

    utils.log(cursor, worker, ident, number, workname,
              'Plugin for work queue item found.')

    change = utils.get_patchset_details(cursor, ident, number)
    git_repo, conflict = utils.create_git(change['project'], change['refurl'],
                                          cursor, worker, ident, number, workname)
    if conflict:
        utils.log(cursor, worker, ident, number, workname,
                  'Git merge failure detected')
        cursor.execute('update work_queue set done="c" where id="%s" and '
                       'number=%s and workname="%s";'
                       % (ident, number, workname))
        cursor.execute('commit;')
        return True

    utils.log(cursor, worker, ident, number, workname,
              'Git checkout created')

    safe_refurl = change['refurl'].replace('/', '_')

    flags = utils.get_config()
    db = workname[len('sqlalchemy_migration_'):]
    cmd = ('/srv/openstack-ci-tools/plugins/test_sqlalchemy_migrations.sh '
           '%(ref_url)s %(git_repo)s %(dbuser)s %(dbpassword)s %(db)s '
           '2>&1'
           % {'ref_url': safe_refurl,
              'git_repo': git_repo,
              'dbuser': flags['test_dbuser'],
              'dbpassword': flags['test_dbpassword'],
              'db': db})
    print 'Executing script: %s' % cmd
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    l = p.stdout.readline()
    while l:
        utils.log(cursor, worker, ident, number, workname, l)
        l = p.stdout.readline()

    return True
