#!/bin/bash
#
# Neutron server monitoring script
#
# Copyright © 2013-2014 eNovance <licensing@enovance.com>
#
# Author: Emilien Macchi <emilien.macchi@enovance.com>
# With the good help of eNovance fellow contributorz :-)
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
# Requirement: curl, netstat
#
set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
DEAMON='neutron-server'
STATE_DEPENDENT=4

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                   Get help"
    echo " -H <Auth URL>        URL for obtaining an auth token. Default: http://localhost:5000/v2.0"
    echo " -E <Endpoint URL>    URL for neutron API. Default: http://localhost:9696/v2.0"
    echo " -T <admin tenant>    Admin tenant name to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use ro get an auth token"
    echo " -m <amqp port>       Port on which your AMQP server is listening. Default: 5672"
}

while getopts 'hH:U:T:P:E:m:' OPTION
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
            export OS_TENANT_NAME=$OPTARG
            ;;
        U)
            export OS_USERNAME=$OPTARG
            ;;
        P)
            export OS_PASSWORD=$OPTARG
            ;;
        m)
            AMQP_PORT=$OPTARG
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

# User must provide at least non-empty parameters
[[ -z "${OS_TENANT_NAME}" || -z "${OS_USERNAME}" || -z "${OS_PASSWORD}" ]] && (usage; exit 1)

# Set default values
OS_AUTH_URL=${OS_AUTH_URL:-"http://localhost:5000/v2.0"}
ENDPOINT_URL=${ENDPOINT_URL:-"http://localhost:9696/v2.0"}
AMQP_PORT=${AMQP_PORT:-5672}

if ! which curl >/dev/null 2>&1 || ! which netstat >/dev/null 2>&1 || ! which python >/dev/null 2>&1
then
    echo "UNKNOWN: curl or netstat are not installed."
    exit $STATE_UNKNOWN
fi

# Try to get an auth token from keystone API
KS_RESP=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"}, "tenantName":"'$OS_TENANT_NAME'"}}' -H 'Content-type: application/json' || true)
if [ ! -z "${KS_RESP}" ]; then
    TOKEN=$(echo ${KS_RESP} | python -c "import sys; import json; data = json.loads(sys.stdin.readline()); print data.get('access',{}).get('token',{}).get('id',{})")
    if [ "${TOKEN}" = "{}" ]; then
        echo "CRITICAL: Unable to get a valid token from Keystone API"
        exit $STATE_CRITICAL
    fi
else
    echo "CRITICAL: Unable to reach Keystone API"
    exit $STATE_CRITICAL
fi

# Check Neutron API
START=$(date +%s)
API_RESP=$(curl -s -H "X-Auth-Token: $TOKEN" -H "Content-type: application/json" ${ENDPOINT_URL}/networks || true)
END=$(date +%s)
if [ ! -z "${API_RESP}" ]; then
    NETWORKS=$(echo ${API_RESP} | python -c "import sys; import json; data = json.loads(sys.stdin.readline()); print data.get('networks',{})")
    if [ "${NETWORKS}" = "{}" ]; then
        echo "CRITICAL: Unable to retrieve a network for tenant ${OS_TENANT_NAME} from Neutron API"
        exit $STATE_CRITICAL
    fi
else
    echo "CRITICAL: Unable to reach Neutron API"
    exit $STATE_CRITICAL
fi

TIME=$((END-START))

PID=$(ps -ef | awk "BEGIN {FS=\" \"}{if (/python(2.7)? [^ ]+${DEAMON}/) {print \$2 ; exit}}")

if [ -z "${PID}" ]; then
    echo "CRITICAL: $DEAMON is not running."
    exit $STATE_CRITICAL
fi

if [ $(id -u) -ne 0 ]; then
    echo "WARNING: $DEAMON is running but the script must be run as root"
    exit $STATE_WARNING
else
    # Need root to run "netstat -p"
    if ! KEY=$(netstat -eptan 2>/dev/null | egrep ":${AMQP_PORT}\ .*.${PID}\/python(2.7)?" 2>/dev/null) || test -z "${KEY}" || test -z "${NETWORKS}"
    then
        echo "CRITICAL: Neutron server is down or does not seem connected to your AMQP server."
        exit $STATE_CRITICAL
    else
        if [ $TIME -gt 10 ]; then
            echo "WARNING: GET /networks from Neutron API took more than 10 seconds, it's too long."
            exit $STATE_WARNING
        else
            echo "OK: Neutron server is up and running (PID ${PID})"
            exit $STATE_OK
        fi
    fi
fi
