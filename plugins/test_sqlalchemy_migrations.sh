#!/bin/bash -ex

# $1 is the safe refs URL
# $2 is the path to the git repo
# $3 is the nova db user
# $4 is the nova db password
# $5 is the nova db name

# Setup the environment
cd $2
source /etc/bash_completion.d/virtualenvwrapper
mkvirtualenv $1 -r tools/pip-requires
toggleglobalsitepackages
export PYTHONPATH=$PYTHONPATH:$2

# Create a nova.conf file
cat - > /etc/nova/nova.conf <<EOF
[DEFAULT]
sql_connection = mysql://$3:$4@localhost/$5?charset=utf8
debug = True
EOF

# Make sure the test DB is up to date with trunk
git checkout master
python bin/nova-manage db sync

# Now run the patchset
git checkout target
time python bin/nova-manage db sync

# Cleanup virtual env
rmvirtualenv $1