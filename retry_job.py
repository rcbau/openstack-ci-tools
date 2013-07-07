#!/usr/bin/python

# Args are:
#  change id
#  number

import sys

import utils
import workunit


cursor = utils.get_cursor()
workunit.recheck(cursor, sys.argv[1], sys.argv[2])
