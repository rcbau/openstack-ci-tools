#!/bin/bash -ex

cp etc/volumes /etc/network/if-up.d/
chmod ugo+rx /etc/network/if-up.d/
pvcreate /dev/xvdb
vgcreate srv /dev/xvdb
lvcreate -L99G -nsrv srv
lvcreate -L100G -nmysql srv
mkfs.ext4 /dev/mapper/srv-srv 
mkfs.ext4 /dev/mapper/srv-mysql

set +e
/etc/network/if-up.d/volumes 
set -e

mkdir /srv/mysql
/etc/network/if-up.d/volumes 
df -h

chown -R mikal.mikal /srv
mkdir /srv/git
mkdir /srv/git-checkouts
mkdir /srv/logs