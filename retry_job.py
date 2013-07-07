#!/usr/bin/python

# Args are:
#  change id
#  number

import sys

import workunit


workunit.recheck(sys.argv[1], sys.argv[2])
