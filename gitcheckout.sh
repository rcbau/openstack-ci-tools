#!/bin/bash -x

# $1 is the git directory
# $2 is the project name
# $3 is the ref url

cd /srv/git/$2
git checkout master
git pull

rm -rf $1 || true
mkdir -p /srv/git-checkouts/$2
cp -Rp /srv/git/$2 $1

cd $1
git checkout -b target
git pull https://review.openstack.org/$2 $3
