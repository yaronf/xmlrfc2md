#!/bin/bash
#

python3.10 ../xmlrfc2md.py $1-orig.xml $1.md
kdrfc --html $1.md
