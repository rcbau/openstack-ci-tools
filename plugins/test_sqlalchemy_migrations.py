#!/usr/bin/python

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
        if filename.find('nova/db/sqlalchemy/versions') != -1:
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

