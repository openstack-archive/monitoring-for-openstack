#!/bin/bash
#
# Glance Image Upload monitoring script for Sensu / Nagios
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

# Random string with 5 chars
RANDOM_STRING=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 5 | head -n 1)

# Script options
TOKEN_FILE="/tmp/token_check_glance_$RANDOM_STRING"
TENANT_ID_FILE="/tmp/tenant_id_check_glance_$RANDOM_STRING"
IMAGE_ID_FILE="/tmp/image_id_check_glance_$RANDOM_STRING"
GLANCE_API_VERSION="v1"

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                   Get help"
    echo " -E <Endpoint URL>    URL for glance API. Ex: http://localhost:9292/v1"
    echo " -H <Auth URL>        URL for obtaining an auth token. Ex: http://localhost:5000/v2.0"
    echo " -T <tenant>          Tenant to use to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use to get an auth token"
    echo " -N <name>            Name of the monitoring image"
}

output_result () {
        # Output check result & refresh cache if requested
        MSG="$1"
        RETCODE=$2

        echo "$MSG"
        exit $RETCODE
}

while getopts 'hH:U:T:P:N:E:' OPTION
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
            export IMAGE_NAME=$OPTARG
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

START=`date +%s`

# Generate an image file (1MB)
( dd if=/dev/zero of=/tmp/"$IMAGE_NAME".img bs=1M count=1 ) > /dev/null 2>&1

# Upload the image
curl -s -d "<open file /tmp/"$IMAGE_NAME".img, mode 'r' at 0x7fc48f5b4151>" -X POST -H "X-Auth-Token: $TOKEN" -H "x-image-meta-container_format: bare" -H "Transfer-Encoding: chunked" -H "User-Agent: python-glanceclient" -H "Content-Type: application/octet-stream" -H "x-image-meta-disk_format: qcow2" -H "x-image-meta-name: $IMAGE_NAME" "$ENDPOINT_URL"/"$GLANCE_API_VERSION"/images | python -mjson.tool | awk -v var="\"id\":" '$0 ~ var { print $2 }' | sed -e 's/"//g' -e 's/,//g' > $IMAGE_ID_FILE
if [ -s $IMAGE_ID_FILE ]
then
        IMAGE_ID=$(cat $IMAGE_ID_FILE)
else
        output_result "CRITICAL - Unable to upload image in Glance" $STATE_CRITICAL
fi

rm -f /tmp/"$IMAGE_NAME".img

# Delete the image
curl -s -H "X-Auth-Token: $TOKEN" "$ENDPOINT_URL"/"$GLANCE_API_VERSION"/images/"$IMAGE_ID" -X DELETE > /dev/null 2>&1

# Cleaning
rm $TOKEN_FILE $TENANT_ID_FILE $IMAGE_ID_FILE 

END=`date +%s`
TIME=$((END-START))

if [ $TIME -gt 60 ]; then
    output_result "CRITICAL - Unable to upload image in Glance" $STATE_CRITICAL
else
    if [ "$TIME" -gt "20" ]; then
            output_result "WARNING - Upload image in 20 seconds, it's too long" $STATE_WARNING
    else
        output_result "OK - Glance image uploaded in $TIME seconds" $STATE_OK
    fi
fi

