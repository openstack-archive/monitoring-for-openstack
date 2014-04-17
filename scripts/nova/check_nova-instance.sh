#!/bin/bash
#
# Nova create instance monitoring script for Sensu / Nagios
#
# Copyright © 2014 eNovance <licensing@enovance.com>
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
# Requirement: curl python
#

# Nagios/Sensu return codes
STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
STATE_DEPENDENT=4

# Script options
REFRESH=0
MAX_AGE=1800
CACHEFILE="/tmp/check_nova-instance.tmp"
TOKEN_FILE="/tmp/token"
TENANT_ID_FILE="/tmp/tenant_id"
IMAGE_ID_FILE="/tmp/image_id"
FLAVOR_ID_FILE="/tmp/flavor_id"
NOVA_ID_FILE="/tmp/nova_id"
INSTANCE_STATUS_FILE="/tmp/instance_status"
EXISTING_INSTANCE_ID_FILE="/tmp/instance_id"

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
	MSG="$1"
	RETCODE=$2
	
	if [ $REFRESH -gt 0 ]
	then 
		echo "$MSG" > $CACHEFILE
		echo $RETCODE >> $CACHEFILE
	fi
	
	echo "$MSG"
	exit $RETCODE
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

if [ -z "$SERVER_NAME" ]
then
	echo "SERVER_NAME not set."
	exit 1
fi

# Read results from cache unless refresh requested
if [ $REFRESH -eq 0 ] 
then
	if [ -f $CACHEFILE ]
	then
		FILEAGE=$(($(date +%s) - $(stat -c '%Y' "$CACHEFILE")))
		if [ $FILEAGE -gt $MAX_AGE ]; then
			output_result "UNKNOWN - Cachefile is older than $MAX_AGE seconds!" $STATE_UNKNOWN
		else
			ARRAY=()
			while read -r LINE; do
				ARRAY+=("$LINE")
			done < $CACHEFILE
			output_result "${ARRAY[0]}" ${ARRAY[1]}
		fi
	else
		output_result "UNKNOWN - Unable to open cachefile !" $STATE_UNKNOWN
	fi
fi

# Set default values
OS_AUTH_URL=${OS_AUTH_URL:-"http://localhost:5000/v2.0"}
ENDPOINT_URL=${ENDPOINT_URL:-"http://localhost:8774/v2"}

if ! which curl > /dev/null 2>&1
then
	output_result "UNKNOWN - curl is not installed." $STATE_UNKNOWN
fi

# Get the token
curl -s -d '{"auth": {"tenantName": "'$OS_TENANT'", "passwordCredentials": {"username": "'$OS_USERNAME'", "password": "'$OS_PASSWORD'"}}}' -H 'Content-type: application/json' "$OS_AUTH_URL"/tokens | python -mjson.tool | awk -v var="\"id\": \"M" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $TOKEN_FILE
if [ -s $TOKEN_FILE ]
then
	TOKEN=$(cat $TOKEN_FILE)
else
	output_result "CRITICAL - Unable to get a token from Keystone API" $STATE_CRITICAL
fi

# Get the tenant ID
curl -s -H "X-Auth-Token: $TOKEN" "$OS_AUTH_URL"/tenants | python -mjson.tool | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $TENANT_ID_FILE
if [ -s $TENANT_ID_FILE ]
then
	TENANT_ID=$(cat $TENANT_ID_FILE)
else
	output_result "CRITICAL - Unable to get tenant ID from Keystone API" $STATE_CRITICAL
fi

# Check if an instance with the same name already exist
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/servers | python -mjson.tool | grep -B11 "$SERVER_NAME" | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $EXISTING_INSTANCE_ID_FILE
if [ -s $EXISTING_INSTANCE_ID_FILE ]
then
	EXISTING_INSTANCE_ID=$(cat $EXISTING_INSTANCE_ID_FILE)
	for TO_DELETE in $EXISTING_INSTANCE_ID
	do
		curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/servers/"$TO_DELETE" -X DELETE
	done
fi

START=`date +%s`

# Get image ID
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/images | python -mjson.tool | grep -B16 "$IMAGE_NAME" | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $IMAGE_ID_FILE
if [ -s $IMAGE_ID_FILE ]
then
	IMAGE_ID=$(cat $IMAGE_ID_FILE)
else
	output_result "CRITICAL - Unable to get image ID from nova API" $STATE_CRITICAL
fi

# Get flavor ID
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/flavors | python -mjson.tool | grep -B11 "$FLAVOR_NAME" | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $FLAVOR_ID_FILE
if [ -s $FLAVOR_ID_FILE ]
then
	FLAVOR_ID=$(cat $FLAVOR_ID_FILE)
else
	output_result "CRITICAL - Unable to get flavor ID from nova API" $STATE_CRITICAL
fi

# Spawn the new instance
curl -s -d '{"server": {"name": "'$SERVER_NAME'", "imageRef": "'$IMAGE_ID'", "flavorRef": "'$FLAVOR_ID'", "max_count": 1, "min_count": 1}}' "$ENDPOINT_URL"/"$TENANT_ID"/servers -X POST -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" | python -mjson.tool | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $NOVA_ID_FILE
if [ -s $NOVA_ID_FILE ]
then
	INSTANCE_ID=$(cat $NOVA_ID_FILE)
else
	output_result "CRITICAL - Unable to get instance ID from nova API" $STATE_CRITICAL
fi

# Get the new instance status
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/servers/"$INSTANCE_ID" | python -mjson.tool | awk -v var="\"status\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $INSTANCE_STATUS_FILE
if [ -s $INSTANCE_STATUS_FILE ]
then
	INSTANCE_STATUS=$(cat $INSTANCE_STATUS_FILE)
else
	output_result "CRITICAL - Unable to get instance status from nova API" $STATE_CRITICAL
fi

# While the instance is not in ACTIVE or ERROR state we check the status
while [ "$INSTANCE_STATUS" != "ACTIVE" ]
do
	sleep 5
   
	# Check the instance status 
	curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/servers/"$INSTANCE_ID" | python -mjson.tool | awk -v var="\"status\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $INSTANCE_STATUS_FILE

	if [ -s $INSTANCE_STATUS_FILE ]
	then
		INSTANCE_STATUS=$(cat $INSTANCE_STATUS_FILE)
	else
		output_result "CRITICAL - Unable to get instance status from nova API" $STATE_CRITICAL
	fi

	if [ "$INSTANCE_STATUS" == "ERROR" ];
	then
		output_result "CRITICAL - Unable to spawn instance" $STATE_CRITICAL
	fi
done

END=`date +%s`
TIME=$((END-START))

# Delete the new instance
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$TENANT_ID"/servers/"$INSTANCE_ID" -X DELETE

# Cleaning
rm $TOKEN_FILE $TENANT_ID_FILE $IMAGE_ID_FILE $FLAVOR_ID_FILE $NOVA_ID_FILE $INSTANCE_STATUS_FILE $EXISTING_INSTANCE_ID_FILE

if [ $TIME -gt 300 ]; then
	output_result "CRITICAL - Unable to spawn instance quickly" $STATE_CRITICAL
else
	if [ $TIME -gt 180 ]; then
		output_result "WARNING - Spawn image in 180 seconds, it's too long" $STATE_WARNING
	else
		output_result "OK - Nova instance spawned in $TIME seconds | time=$TIME" $STATE_OK
	fi
fi
