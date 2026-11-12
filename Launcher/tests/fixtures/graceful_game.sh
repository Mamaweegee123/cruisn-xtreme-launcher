#!/bin/sh
trap 'sleep 0.25; exit 0' TERM INT
printf '%s\n' "graceful fixture started: $1"
while :; do
    sleep 1
done
