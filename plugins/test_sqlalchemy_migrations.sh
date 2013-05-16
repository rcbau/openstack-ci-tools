#!/bin/bash

# $1 is the safe refs URL
# $2 is the path to the git repo
# $3 is the nova db user
# $4 is the nova db password
# $5 is the nova db name

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=/srv/cache/pip

cd $2
git checkout master
git pull

source /etc/bash_completion.d/virtualenvwrapper
mkvirtualenv $1
pip install -r tools/pip-requires
toggleglobalsitepackages
export PYTHONPATH=$PYTHONPATH:$2

# Create a nova.conf file
cat - > /etc/nova/nova.conf <<EOF
[DEFAULT]
sql_connection = mysql://$3:$4@localhost/$5?charset=utf8
log_file = 
verbose = True
EOF

# Make sure the test DB is up to date with trunk
python bin/nova-manage db sync

# Now run the patchset
git checkout target
pip install -r tools/pip-requires

echo "***** DB Upgrade Begins *****"
time python bin/nova-manage db sync
echo "***** DB Upgrade Ends *****"

# Cleanup virtual env
deactivate
rmvirtualenv $1
