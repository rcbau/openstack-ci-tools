#!/bin/bash

# $1 is the safe refs URL
# $2 is the path to the git repo
# $3 is the nova db user
# $4 is the nova db password
# $5 is the nova db name

# Setup the environment
cd $2
export PYTHONPATH=$PYTHONPATH:$2
source /etc/bash_completion.d/virtualenvwrapper
mkvirtualenv $1
pip install -r tools/pip-requires
toggleglobalsitepackages

# Create a nova.conf file
cat - > /etc/nova/nova.conf <<EOF
[DEFAULT]
sql_connection = mysql://$3:$4@localhost/$5?charset=utf8
log_file = 
debug = True
EOF

# Make sure the test DB is up to date with trunk
git checkout master
python bin/nova-manage db sync

# Now run the patchset
git checkout target
time python bin/nova-manage db sync

# Cleanup virtual env
deactivate
rmvirtualenv $1
