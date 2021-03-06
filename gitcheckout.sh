#!/bin/bash -x

# $1 is the git directory
# $2 is the project name
# $3 is the ref url
# $4 is how far to rewind master

cd /srv/git/$2
git checkout master
git pull
git checkout stable/grizzly
git pull
git checkout master

rm -rf $1 || true
mkdir -p /srv/git-checkouts/$2
cp -Rp /srv/git/$2 $1

cd $1
if [ $4 -gt 0 ]
then
  git checkout HEAD~$4
fi

git checkout -b trunk
git fetch https://review.openstack.org/$2 $3
git checkout FETCH_HEAD
git checkout -b target

# We need to rebase to pull in deltas between trunk and the point where this
# patch diverged from trunk.
git rebase origin