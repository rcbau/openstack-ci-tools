#!/bin/bash

# $1 is the safe refs URL
# $2 is the path to the git repo
# $3 is the nova db user
# $4 is the nova db password
# $5 is the nova db name

pip_requires() {
  requires="tools/pip-requires"
  if [ ! -e $requires ]
  then
    requires="requirements.txt"
  fi
  echo "Install pip requirements from $requires"
  pip install -q -r $requires
}

db_sync() {
  echo "***** DB upgrade to state of $1 starts *****"
  nova_manage="$2/bin/nova-manage"
  python $nova_manage db sync
  echo "***** DB upgrade to state of $1 finished *****"
}

echo "To execute this script manually, run this:"
echo "$0 $1 $2 $3 $4 $5"

set -x

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=/srv/cache/pip

# Restore database to known good state
echo "Restoring test database $5"
mysql -u $3 --password=$4 $5 < /srv/datasets/$5.sql

echo "Build test environment"
cd $2
git checkout master
git pull

set +x
echo "Setting up virtual env"
source ~/.bashrc
source /etc/bash_completion.d/virtualenvwrapper
mkvirtualenv $1
toggleglobalsitepackages
set -x
export PYTHONPATH=$PYTHONPATH:$2

# Create a nova.conf file
cat - > /etc/nova/nova.conf <<EOF
[DEFAULT]
sql_connection = mysql://$3:$4@localhost/$5?charset=utf8
log_file = 
verbose = True
EOF

# Some databases are from Folsom
version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema version is $version"
if [ $version == "133" ]
then
  echo "Database is from Folsom! Upgrade via grizzly"
  git checkout stable/grizzly
  git pull
  pip_requires
  db_sync "grizzly" $2
  git checkout master
fi

# Make sure the test DB is up to date with trunk
echo "Update database to current state of master"
pip_requires
db_sync "master" $2

# Now run the patchset
echo "Now test the patchset"
git checkout target
git rebase origin
pip_requires

db_sync "patchset" $2

# Cleanup virtual env
set +x
echo "Cleaning up virtual env"
deactivate
rmvirtualenv $1
