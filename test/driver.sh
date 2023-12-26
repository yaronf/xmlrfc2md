#!/bin/bash

first=8950
last=9000

rfcnum=$first
while [ $rfcnum -le $last ]; do
	echo $rfcnum
	url="https://www.rfc-editor.org/rfc/rfc$rfcnum.xml"
	# curl $url > rfc$rfcnum-orig.xml
	infile=rfc$rfcnum-orig.xml
	outfile=rfc$rfcnum.md
	python3.10 ../xmlrfc2md.py $infile $outfile
	rfcnum=$(($rfcnum+1))
done

