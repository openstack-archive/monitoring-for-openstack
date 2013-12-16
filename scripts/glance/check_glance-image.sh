#!/bin/bash
#
# Glance Image Upload monitoring script for Sensu / Nagios
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
    echo " -h                   Get help"
    echo " -E <Endpoint URL>    URL for glance API. Ex: http://localhost:9292/v1"
    echo " -H <Auth URL>        URL for obtaining an auth token. Ex: http://localhost:5000/v2.0"
    echo " -T <tenant>          Tenant to use to get an auth token"
    echo " -U <username>        Username to use to get an auth token"
    echo " -P <password>        Password to use to get an auth token"
    echo " -N <name>            Name of the monitoring image"
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
    echo "curl is not installed."
    exit $STATE_UNKNOWN
fi

# Get a token from Keystone
TOKEN=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'" ,"tenant":"'$OS_TENANT'"}}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

# Use the token to get a tenant ID. By default, it takes the second tenant
TENANT_ID=$(curl -s -H "X-Auth-Token: $TOKEN" ${OS_AUTH_URL}/tenants |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["tenants"][0]["id"]')

# Get a second tenant to avoid the 401 from Glance
TOKEN_TENANT=$(curl -s -X 'POST' ${OS_AUTH_URL}/tokens -d '{"auth":{"passwordCredentials":{"username": "'$OS_USERNAME'", "password":"'$OS_PASSWORD'"} ,"tenantId":"'$TENANT_ID'"}}' -H 'Content-type: application/json' |python -c 'import sys; import json; data = json.loads(sys.stdin.readline()); print data["access"]["token"]["id"]')

if [ -z "$TOKEN_TENANT" ]; then
    echo "Unable to get a token from Keystone API"
    exit $STATE_CRITICAL
fi

START=`date +%s`

# Generate an image file (1MB)
( dd if=/dev/zero of=/tmp/${IMAGE_NAME}.img bs=1M count=1 ) > /dev/null 2>&1

# Upload the image
IMAGE=$(curl -s -i -X POST -H "X-Auth-Token: $TOKEN_TENANT" -H "x-image-meta-container_format: bare" -H "Transfer-Encoding: chunked" -H "User-Agent: python-glanceclient" -H "Content-Type: application/octet-stream" -H "x-image-meta-disk_format: qcow2" -H "x-image-meta-name: $IMAGE_NAME" -d "<open file /tmp/${IMAGE_NAME}.img, mode 'r' at 0x7fc48f5b4150>" ${ENDPOINT_URL}/images)

# Get the image ID
IMAGE_ID=$(echo $IMAGE | awk  '{ n=split($0,a,",") ; for (i=1; i<=n; i++) print a[i] }' | awk -v var="id" '$0 ~ var { print $2 }' | sed 's/"//g')

rm -f /tmp/${IMAGE_NAME}.img

# Delete the image
curl -s -X DELETE -H "X-Auth-Token: $TOKEN_TENANT" -H "Content-Type: application/octet-stream" -H "User-Agent: python-glanceclient" ${ENDPOINT_URL}/images/${IMAGE_ID} > /dev/null 2>&1

END=`date +%s`
TIME=$((END-START))

if [[ "$TIME" -gt "60" ]]; then
    echo "Unable to upload image"
    exit $STATE_CRITICAL
else
    if [ "$TIME" -gt "10" ]; then
        echo "Upload image in 10 seconds, it's too long."
        exit $STATE_WARNING
    else
        echo "Glance image uploaded in $TIME seconds."
        exit $STATE_OK
    fi
fi
