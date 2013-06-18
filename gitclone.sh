#!/bin/bash -x

# $1 is the project owner (openstack, stackforge, etc)
# $2 is the project name

mkdir -p /srv/git/$1
cd /srv/git/$1
git clone https://anonymous:anonymous@github.com/$1/$2.git
