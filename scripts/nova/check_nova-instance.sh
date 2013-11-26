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

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -H <Auth URL>    URL for obtaining an auth token. Ex: http://localhost"
    echo " -T <tenant>      Tenant to use to get an auth token"
    echo " -U <username>    Username to use to get an auth token"
    echo " -P <password>    Password to use ro get an auth token"
    echo " -N <server name> Name of the monitoring instance"
    echo " -I <image name>  Name of the Glance image"
    echo " -F <flavor name> Name of the Nova flavor"
}

while getopts 'h:H:U:T:P:N:I:F:' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        H)
            export OS_AUTH_URL=$OPTARG
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
        *)
            usage
            exit 1
            ;;
    esac
done

if ! which curl >/dev/null 2>&1
then
    echo "curl is not installed."
    exit $STATE_UNKNOWN
fi

##### TOKEN PART #####
# Get a token from Keystone
TOKEN=$(curl -s -X 'POST' ${OS_AUTH_URL}:5000/v2.0/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'" ,"tenant":"'$OS_TENANT'"}}}' -H 'Content-type: application/json' |sed -e 's/[{}]/''/g' | awk -v k="text" '{n=split($0,a,","); for (i=1; i<=n; i++) print a[i]}'|awk 'NR==2'|awk '{print $2}'|sed -n 's/.*"\([^"]*\)".*/\1/p')

# Use the token to get a tenant ID. By default, it takes the second tenant
TENANT_ID=$(curl -s -H "X-Auth-Token: $TOKEN" ${OS_AUTH_URL}:5000/v2.0/tenants |sed -e 's/[{}]/''/g' | awk -v k="text" '{n=split($0,a,","); for (i=1; i<=n; i++) print a[i]}'|grep id|awk 'NR==1'|awk '{print $2}'|sed -n 's/.*"\([^"]*\)".*/\1/p')

# Get a second token to avoid 401 error
TOKEN_TENANT=$(curl -s -X 'POST' ${OS_AUTH_URL}:5000/v2.0/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"} ,"tenantId":"'$TENANT_ID'"}}' -H 'Content-type: application/json' |sed -e 's/[{}]/''/g' | awk -v k="text" '{n=split($0,a,","); for (i=1; i<=n; i++) print a[i]}'|awk 'NR==2'|awk '{print $2}'|sed -n 's/.*"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN_TENANT" ]; then
    echo "Unable to get a token from Keystone API"
    exit $STATE_CRITICAL
fi

START=`date +%s`

##### INSTANCE PART #####
# Get image ID
IMAGE_ID=$(curl -s -i ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/images -X GET -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | grep -B8 "$IMAGE_NAME" | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Get flavor ID
FLAVOR_ID=$(curl -s -i ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/flavors -X GET -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | grep -A1 "$FLAVOR_NAME" | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Spawn the new instance
INSTANCE=$(curl -s -i ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/servers -X POST -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Content-Type: application/json" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" -d '{"server": {"name": "'$SERVER_NAME'", "imageRef": "'$IMAGE_ID'", "flavorRef": "'$FLAVOR_ID'", "max_count": 1, "min_count": 1, "networks": [], "security_groups": [{"name": "default"}]}}')

# Get the new instance ID
INSTANCE_ID=$(echo $INSTANCE | awk  '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

# Get the new instance status
INSTANCE_STATUS=$(curl -s -i ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/servers/${INSTANCE_ID} -X GET -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,"{") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="status" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g')

# While the instance is not in ACTIVE or ERROR state we check the status
while [ "$INSTANCE_STATUS" != "ACTIVE"  ]
do
    sleep 5
   
    # Check the instance status 
    INSTANCE_STATUS=$(curl -s -i ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/servers/${INSTANCE_ID} -X GET -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT" | awk '{ n=split($0,a,"{") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="status" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g')

    if [ "$INSTANCE_STATUS" == "ERROR" ];
    then
        exit $STATE_CRITICAL
    fi
done

END=`date +%s`
TIME=$((END-START))

# Delete the new instance
curl -s ${OS_AUTH_URL}:8774/v2/${TENANT_ID}/servers/${INSTANCE_ID} -X DELETE -H "X-Auth-Project-Id: $OS_TENANT" -H "User-Agent: python-novaclient" -H "Accept: application/json" -H "X-Auth-Token: $TOKEN_TENANT"

if [[ "$TIME" -gt "300" ]]; then
    echo "Unable to spawn instance."
    exit $STATE_CRITICAL
else
    if [ "$TIME" -gt "180" ]; then
        echo "Spawn image in 180 seconds, it's too long."
        exit $STATE_WARNING
    else
        echo "Nova instance spawned in $TIME seconds."
        exit $STATE_OK
    fi
fi
