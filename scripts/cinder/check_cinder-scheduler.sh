#!/bin/bash
#
# Cinder Scheduler monitoring script for Sensu
#
# Copyright © 2013 eCindernce <licensing@ecindernce.com>
#
# Author: Emilien Macchi <emilien.macchi@ecindernce.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Requirement: netstat
#
set -e

STATE_OK=0
STATE_CRITICAL=2
STATE_UNKNOWN=3

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo "No parameter : Just run the script"
}

while getopts 'h:H:U:T:P:' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if ! which netstat >/dev/null 2>&1
then
    echo "netstat is not installed."
    exit $STATE_UNKNOWN
fi

PID=$(pidof -x cinder-scheduler)

if ! KEY=$(netstat -epta 2>/dev/null | grep $PID 2>/dev/null | grep amqp) || test -z $PID
then
    echo "cinder-scheduler is not connected to AMQP."
    exit $STATE_CRITICAL
fi

echo "cinder-scheduler is working."
exit $STATE_OK
