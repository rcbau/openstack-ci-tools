#!/bin/bash

git pull

apt-get update
apt-get dist-upgrade
apt-get install git python-pip git-review libxml2-dev libxml2-utils libxslt-dev libmysqlclient-dev pep8 postgresql-server-dev-9.1 python2.7-dev python-coverage python-netaddr python-mysqldb mysql-server

cp etc/my.cnf /etc/mysql/
cp etc/usr.sbin.mysqld /etc/apparmor.d/

mkdir -p /var/log/mysql
touch /var/log/mysql/slow-queries.log
chown mysql.mysql /var/log/mysql/slow-queries.log

chmod ugo+rx /var/log/mysql
chmod ugo+r /var/log/syslog /var/log/mysql/slow-queries.log /var/log/mysql/error.log

chown -R mysql.mysql /srv/mysql

/etc/init.d/apparmor restart
/etc/init.d/mysql restart
