#!/bin/bash

# Glance API monitoring script for Sensu / Nagios
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
    echo " -h                   Get help"
    echo " -E <Endpoint URL>    URL for glance API. Ex: http://localhost:9292/v1"
    echo " -H <Auth URL>        URL for obtaining an auth token. Ex: http://localhost:5000/v2.0"
    echo " -T <tenant>          Tenant to use to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use to get an auth token"
}

while getopts 'hH:U:T:P:E:' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        H)
            export OS_AUTH_URL=$OPTARG
            ;;
        E)
            export ENDPOINT_URL=$OPTARG
            ;;
        T)
            export OS_TENANT=$OPTARG
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
ENDPOINT_URL=${ENDPOINT_URL:-"http://localhost:9292/v1"}

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

# Get a token from Keystone
TOKEN=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'" ,"tenant":"'$OS_TENANT'"}}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

if [ -z "$TOKEN" ]; then
    echo "Unable to get token #1 from Keystone API"
    exit $STATE_CRITICAL
fi

# Use the token to get a tenant ID. By default, it takes the second tenant
TENANT_ID=$(curl -s -H "X-Auth-Token: $TOKEN" ${OS_AUTH_URL}/tenants |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["tenants"][0]["id"]')

if [ -z "$TENANT_ID" ]; then
    echo "Unable to get my tenant ID from Keystone API"
    exit $STATE_CRITICAL
fi

# Once we have the tenant ID, we can request a token that will have access to the Glance API
TOKEN2=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"} ,"tenantId":"'$TENANT_ID'"}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

if [ -z "$TOKEN2" ]; then
    echo "Unable to get token #2 from Keystone API"
    exit $STATE_CRITICAL
fi

START=`date +%s.%N`
IMAGES=$(curl -s -H "X-Auth-Token: $TOKEN2" -H 'Content-Type: application/json' -H 'User-Agent: python-glanceclient' ${ENDPOINT_URL}/images/detail?sort_key=name&sort_dir=asc&limit=100)
N_IMAGES=$(echo $IMAGES |  grep -Po '"name":.*?[^\\]",'| wc -l)
END=`date +%s.%N`
TIME=`echo ${END} - ${START} | bc`

if [[ ! "$IMAGES" == *status* ]]; then
    echo "Unable to list images"
    exit $STATE_CRITICAL
else
    if [ `echo ${TIME}'>'10 | bc -l` -gt 0 ]; then
        echo "Get images took 10 seconds, it's too long.|response_time=${TIME}"
        exit $STATE_WARNING
    else
        echo "Get images, Glance API is working: list $N_IMAGES images in $TIME seconds.|response_time=${TIME}"
        exit $STATE_OK
    fi
fi
