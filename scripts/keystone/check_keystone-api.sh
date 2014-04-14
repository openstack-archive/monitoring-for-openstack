#!/bin/bash
#
# Keystone API monitoring script
#
# Copyright © 2013 eNovance <licensing@enovance.com>
#
# Author: Emilien Macchi <emilien.macchi@enovance.com>
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
# Requirement: curl, bc
#
set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
STATE_DEPENDENT=4

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -H <Auth URL>    URL for obtaining an auth token. Ex : http://localhost:5000/v2.0"
    echo " -U <username>    Username to use to get an auth token"
    echo " -P <password>    Password to use ro get an auth token"
}

while getopts 'hH:U:P:' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        H)
            export OS_AUTH_URL=$OPTARG
            ;;
        U)
            export OS_USERNAME=$OPTARG
            ;;
        P)
            export OS_PASSWORD=$OPTARG
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

# Set default values
OS_AUTH_URL=${OS_AUTH_URL:-"http://localhost:5000/v2.0"}

if ! which curl >/dev/null 2>&1
then
    echo "curl is not installed."
    exit $STATE_UNKNOWN
fi

if ! which bc >/dev/null 2>&1
then
    echo "bc is not installed."
    exit $STATE_UNKNOWN
fi

START=`date +%s.%N`
TOKEN=$(curl -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"}}}' -H 'Content-type: application/json' 2>&1 | grep token|awk '{print $6}'|grep -o '".*"' | sed -n 's/.*"\([^"]*\)".*/\1/p')
END=`date +%s.%N`
TIME=`echo ${END} - ${START} | bc`

if [ -z "$TOKEN" ]; then
    echo "Unable to get a token"
    exit $STATE_CRITICAL
else
    if [ `echo ${TIME}'>'10 | bc -l` -gt 0 ]; then
        echo "Got a token after 10 seconds, it's too long.|response_time=${TIME}"
        exit $STATE_WARNING
    else
        echo "Got a token, Keystone API is working.|response_time=${TIME}"
        exit $STATE_OK
    fi
fi
