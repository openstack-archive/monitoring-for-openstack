#!/bin/bash
#
# Neutron server monitoring script
#
# Copyright © 2013-2014 eNovance <licensing@enovance.com>
#
# Author: Emilien Macchi <emilien.macchi@enovance.com>
#         Nicolas Auvray <nicolas.auvray@enovance.com>
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
# Requirement: curl, netstat, awk, bc
#

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
DEAMON='neutron-server'

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                   Get help"
    echo ""
    echo "Required parameters :"
    echo " -T <tenant name>     Tenant name to use to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use to get an auth token"
    echo ""
    echo "Optional parameters :"
    echo " -H <Auth URL>        URL for obtaining an auth token. Default: http://localhost:5000/v2.0"
    echo " -E <Endpoint URL>    URL for neutron API. Default is to get endpoint URL from keystone catalog. Example: http://localhost:9696"
    echo " -m <AMQP port>       Port on which your AMQP server is listening. Default: 5672"
    echo " -k <timeout>         Timeout for Keystone APIs calls. Default to 5 seconds"
    echo " -w <warning>         Warning timeout for Neutron API calls. Default to 5 seconds"
    echo " -c <critical>        Critical timeout for Neutron API calls. Default to 10 seconds"
}

while getopts 'hH:U:T:P:E:m:k:w:c:' OPTION
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
            [[ $OPTARG =~ ^[0-9]+$ ]] && export AMQP_PORT=$OPTARG || (echo "AMQP port must be an entire numeric value"; usage)
            ;;
        k)
            [[ $OPTARG =~ ^[0-9]+$ ]] && export KS_TIMEOUT=$OPTARG || (echo "Keystone timeout must be an entire numeric value"; usage)
            ;;
        w)
            [[ $OPTARG =~ ^[0-9]+$ ]] && export W_TIMEOUT=$OPTARG || (echo "Warning timeout must be an entire numeric value"; usage)
            ;;
        c)
            [[ $OPTARG =~ ^[0-9]+$ ]] && export C_TIMEOUT=$OPTARG || (echo "Critical timeout must be an entire numeric value"; usage)
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

# User must provide at least non-empty parameters
[[ -z "${OS_TENANT_NAME}" || -z "${OS_USERNAME}" || -z "${OS_PASSWORD}" ]] && (usage; exit 1)
# If not timeout is specified
[[ -z $KS_TIMEOUT ]] && export KS_TIMEOUT=5
[[ -z $W_TIMEOUT ]] && export W_TIMEOUT=5
[[ -z $C_TIMEOUT ]] && export C_TIMEOUT=10

# Set default values
OS_AUTH_URL=${OS_AUTH_URL:-"http://localhost:5000/v2.0"}
ENDPOINT_URL=${ENDPOINT_URL:-"$(keystone catalog --service network|grep publicURL|cut -d'|' -f3|sed 's/\s*//g')"}
AMQP_PORT=${AMQP_PORT:-5672}

# Requirements
[ ! which curl >/dev/null 2>&1 ] && (echo "curl is not installed.";exit $STATE_UNKNOWN)
[ ! which bc >/dev/null 2>&1 ] && (echo "bc is not installed.";exit $STATE_UNKNOWN)
[ ! which awk >/dev/null 2>&1 ] && (echo "awk is not installed.";exit $STATE_UNKNOWN)
[ ! which netstat >/dev/null 2>&1 ] && (echo "netstat is not installed.";exit $STATE_UNKNOWN)

# return a json value (key=value, num=position)
function getJson() {
    KEY=$1
    num=$2
    awk -F"[,:}]" '{for(i=1;i<=NF;i++){if($i~/'$KEY'\042/){print $(i+1)}}}' | tr -d '"' | sed -n ${num}p | sed 's/^ //'
}

# Try to get an auth token from keystone API
KS_RESP=$(curl -s -m $KS_TIMEOUT -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"}, "tenantName":"'$OS_TENANT_NAME'"}}' -H 'Content-type: application/json' || :)
if [ ! -z "${KS_RESP}" ]; then
    # We take the 1st ID value as it represents the token ID
    TOKEN=$(echo ${KS_RESP} | getJson id 1)
    if [ -z "${TOKEN}" ]; then
        echo "CRITICAL: Unable to get a token from Keystone API"
        exit $STATE_CRITICAL
    fi
else
    echo "CRITICAL: Unable to reach Keystone API"
    exit $STATE_CRITICAL
fi

# Check Neutron API and calculate the time
START=$(date +%s.%N)
API_RESP=$(curl -s -m $C_TIMEOUT -H "X-Auth-Token: $TOKEN" -H "Content-type: application/json" ${ENDPOINT_URL}/v2.0/networks.json || :)
END=$(date +%s.%N)
if [ ! -z "${API_RESP}" ]; then
    # We take the name of the first network found
    NETWORKS=$(echo ${API_RESP} | getJson name 1)
    if [ "${API_RESP}" = "{}" ]; then
        echo "CRITICAL: Unable to retrieve a network for tenant ${OS_TENANT_NAME} from Neutron API"
        exit $STATE_CRITICAL
    fi
else
    echo "CRITICAL: Unable to contact Neutron API. Either Neutron service is not running or timeout of ${C_TIMEOUT}s has been reached."
    exit $STATE_CRITICAL
fi
TIME=$(echo ${END} - ${START} | bc)

PID=$(ps -ef | awk "BEGIN {FS=\" \"}{if (/python(2.7)? [^ ]+${DEAMON}/) {print \$2 ; exit}}")

if [ -z "${PID}" ]; then
    echo "CRITICAL: $DEAMON is not running."
    exit $STATE_CRITICAL
fi

if [ $(id -u) -ne 0 ]; then
    echo "WARNING: $DEAMON is running but the script must be run as root|response_time=${TIME}"
    exit $STATE_WARNING
else
    # Need root to run "netstat -p"
    if ! KEY=$(netstat -eptan 2>/dev/null | egrep ":${AMQP_PORT}\ .*.${PID}\/python(2.7)?" 2>/dev/null) || test -z "${KEY}" || test -z "${NETWORKS}"
    then
        echo "CRITICAL: Neutron server is down or does not seem connected to your AMQP server."
        exit $STATE_CRITICAL
    else
        if [ $(echo ${TIME}'>'$W_TIMEOUT | bc -l) -gt 0 ]; then
            echo "WARNING: GET /v2.0/networks.json from Neutron API took more than $W_TIMEOUT seconds, it's too long.|response_time=${TIME}"
            exit $STATE_WARNING
        else
            echo "OK: Neutron server is up and running (PID ${PID})|reponse_time=${TIME}"
            exit $STATE_OK
        fi
    fi
fi
