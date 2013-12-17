#!/bin/bash
#
# Nova create instance monitoring script for Sensu / Nagios
#
# Copyright © 2013 eNovance <licensing@enovance.com>
#
# Author: Gaëtan Trellu <gaetan.trellu@enovance.com>
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
# Requirement: curl
#
set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
STATE_DEPENDENT=4
REFRESH=0
MAX_AGE=1800
CACHEFILE='/tmp/check_nova-instance.tmp'

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                   Get help"
    echo " -H <Auth URL>        URL for obtaining an auth token. Ex: http://localhost:5000/v2.0"
    echo " -E <Endpoint URL>    URL for nova API. Ex: http://localhost:8774/v2"
    echo " -T <tenant>          Tenant to use to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use ro get an auth token"
    echo " -N <server name>     Name of the monitoring instance"
    echo " -I <image name>      Name of the Glance image"
    echo " -F <flavor name>     Name of the Nova flavor"
    echo " -r                   Refresh the cache"
}

output_result () {
    # Output check result & refresh cache if requested
    msg="$1"
    retcode=$2
    if [ $REFRESH -gt 0 ]
    then 
        echo "$msg">$CACHEFILE
        echo $retcode>>$CACHEFILE
    fi
    echo "$msg"
    exit $retcode
}

while getopts 'hH:U:T:P:N:I:F:E:r' OPTION
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
        N)
            export SERVER_NAME=$OPTARG
            ;;
        I)
            export IMAGE_NAME=$OPTARG
            ;;
        F)
            export FLAVOR_NAME=$OPTARG
            ;;
        r)
            export REFRESH=1
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done



# Read results from cache unless refresh requested

if [ $REFRESH -eq 0 ] 
then
    if [ -f $CACHEFILE ]
    then
        FILEAGE=$(($(date +%s) - $(stat -c '%Y' "$CACHEFILE")))
        if [ $FILEAGE -gt $MAX_AGE ]; then
            output_result "Cachefile is older than $MAX_AGE seconds!" $STATE_UNKNOWN
        else
            ARRAY=()
            while read -r line; do
                ARRAY+=("$line")
            done < $CACHEFILE
            output_result "${ARRAY[0]}" ${ARRAY[1]}
        fi
    else
        output_result "Unable to open cachefile!" $STATE_UNKNOWN
    fi
fi

# Set default values
OS_AUTH_URL=${OS_AUTH_URL:-"http://localhost:5000/v2.0"}
ENDPOINT_URL=${ENDPOINT_URL:-"http://localhost:8774/v2"}

if ! which curl >/dev/null 2>&1
then
    output_result "curl is not installed." $STATE_UNKNOWN
fi

##### TOKEN PART #####
# Get a token from Keystone
TOKEN=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'" ,"tenant":"'$OS_TENANT'"}}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

# Use the token to get a tenant ID. By default, it takes the second tenant
TENANT_ID=$(curl -s -H "X-Auth-Token: $TOKEN" ${OS_AUTH_URL}/tenants |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["tenants"][0]["id"]')

# Get a second token to avoid 401 error
TOKEN_TENANT=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"} ,"tenantId":"'$TENANT_ID'"}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

if [ -z "$TOKEN_TENANT" ]; then
    output_result "Unable to get a token from Keystone API" $STATE_CRITICAL
fi

START=`date +%s`

##### INSTANCE PART #####
# Get image ID
IMAGE_ID=$(curl -s -i ${ENDPOINT_URL}/${TENANT_ID}/images -X GET -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | grep -B8 "$IMAGE_NAME" | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Get flavor ID
FLAVOR_ID=$(curl -s -i ${ENDPOINT_URL}/${TENANT_ID}/flavors -X GET -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | grep -A1 "$FLAVOR_NAME" | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Spawn the new instance
INSTANCE=$(curl -s -i ${ENDPOINT_URL}/${TENANT_ID}/servers -X POST -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Content-Type: application/json" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" -d '{"server": {"name": "'$SERVER_NAME'", "imageRef": "'$IMAGE_ID'", "flavorRef": "'$FLAVOR_ID'", "max_count": 1, "min_count": 1, "networks": [], "security_groups": [{"name": "default"}]}}')

# Get the new instance ID
INSTANCE_ID=$(echo $INSTANCE | awk  '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Get the new instance status
INSTANCE_STATUS=$(curl -s -i ${ENDPOINT_URL}/${TENANT_ID}/servers/${INSTANCE_ID} -X GET -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,"{") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="status" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g')

# While the instance is not in ACTIVE or ERROR state we check the status
while [ "$INSTANCE_STATUS" != "ACTIVE"  ]
do
    sleep 5
   
    # Check the instance status 
    INSTANCE_STATUS=$(curl -s -i ${ENDPOINT_URL}/${TENANT_ID}/servers/${INSTANCE_ID} -X GET -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,"{") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="status" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g')

    if [ "$INSTANCE_STATUS" == "ERROR" ];
    then
        output_result "ERROR" $STATE_CRITICAL
    fi
done

END=`date +%s`
TIME=$((END-START))

# Delete the new instance
curl -s ${ENDPOINT_URL}/${TENANT_ID}/servers/${INSTANCE_ID} -X DELETE -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT"

if [[ "$TIME" -gt "300" ]]; then
    output_result "Unable to spawn instance." $STATE_CRITICAL
else
    if [ "$TIME" -gt "180" ]; then
        output_result "Spawn image in 180 seconds, it's too long." $STATE_WARNING
    else
        output_result "Nova instance spawned in $TIME seconds. | time=$TIME" $STATE_OK
    fi
fi
