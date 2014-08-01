#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Keystone monitoring script for Nagios
#
# Copyright © 2012-2014 eNovance <licensing@enovance.com>
#
# Authors:
#   Sofer Athlan-Guyot <sofer.athlan@enovance.com>
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
# Requirments: python-cinderclient, python-argparse, python
# ## Arguments
# 
# ### Required arguments
# * `--auth_url`: Keystone URL
# * `--username`: Username to use for authentication
# * `--password`: Password to use for authentication
# * `--tenant`: Tenant name to use for authentication
# 
# ### Optional arguments
# 
# * `-h`: Show the help message and exit
# * `--region_name`: Region to select for authentication
# * `--endpoint_url`: Override the catalog endpoint
# * `--endpoint_type`: When not overriding, which type to use in the catalog.  Public by default.
# * `--volume_name`: Name of the volume to create (monitoring_test by default)
# * `--volume_size`: Size of the volume to create (1 GB by default)
# * `--volume_type`: With multiple backends, choose the volume type.
# * `--availability_zone`: Specify availability zone.
# * `--force_delete`: If matching volumes are found, delete them and add a notification in the message instead of getting out in critical state.
# * `--api_version`: Version of the API to use. 1 by default.
# * `--timeout`: Max number of second to create/destroy a volume (120 by default).
# * `--verbose`: Print requests on stderr
# 
# ## Usage
# 
# Create a test volume and delete it, only if no volume match
# `volume_name` (here `monitoring_test` by default).  If there is any
# volume it assumes that it's some leftover and exit in CRITICAL state,
# notifying the rogue volumes.  Good for testing that everything works
# properly in your environment.
# 
# * `check_cinder-volume.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD`
# 
# Here we mangle the endpoint url to override the one returned by the
# catalog.  If we assume that the url returned by the catalog is behind
# a load balancer, this enable the user to easely choose which API
# server it's going to query.
# 
# * `check_cinder-volume.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD --endpoint_url http://localhost`
# 
# Here we force de deletion of any volume found with the matching name.
# The number of found volume is returned in the output of the plugin.
# 
# * `check_cinder-volume.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD --force_delete`
# 
# For a asynchronous usage relative to a nagios check, one can use
# [cache_check.py](https://github.com/gaelL/nagios-cache-check)
# 
# * `cache_check.py -c "check_cinder-volume.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD"`
# 
import os
import sys
import argparse
from cinderclient.client import Client
from cinderclient import exceptions
import time
import logging
import urlparse
from datetime import datetime

DAEMON_DEFAULT_PORT = 8776

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3


def script_unknown(msg):
    sys.stderr.write("UNKNOWN - %s (UTC: %s)\n" % (msg, datetime.utcnow()))
    sys.exit(STATE_UNKNOWN)


def script_critical(msg):
    sys.stderr.write("CRITICAL - %s (UTC: %s)\n" % (msg, datetime.utcnow()))
    sys.exit(STATE_CRITICAL)


# python has no "toepoch" method: http://bugs.python.org/issue2736
# now, after checking http://stackoverflow.com/a/16307378,
# and http://stackoverflow.com/a/8778548 made my mind to this approach
def totimestamp(dt=None, epoch=datetime(1970, 1, 1)):
    if not dt:
        dt = datetime.utcnow()
    td = dt - epoch
    # return td.total_seconds()
    return int((td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6)
               / 1e6)


class Novautils:
    def __init__(self, nova_client):
        self.nova_client = nova_client
        self.msgs = []
        self.start = totimestamp()
        self.notifications = ["volume_creation_time=%s" % self.start]
        self.volume = None
        self.connection_done = False

    def check_connection(self, force=False):
        if not self.connection_done or force:
            try:
                # force a connection to the server
                self.connection_done = self.nova_client.limits.get()
            except Exception as e:
                script_critical("Cannot connect to cinder: %s" % e)

    def get_duration(self):
        return totimestamp() - self.start

    def mangle_url(self, url):
        # This first connection populate the structure we need inside
        # the object.  This does not cost anything if a connection has
        # already been made.
        self.check_connection()
        try:
            endpoint_url = urlparse.urlparse(url)
        except Exception as e:
            script_unknown("you must provide an endpoint_url in the form"
                           + "<scheme>://<url>/ (%s)" % e)
        scheme = endpoint_url.scheme
        if scheme is None:
            script_unknown("you must provide an endpoint_url in the form"
                           + "<scheme>://<url>/ (%s)" % e)
        catalog_url = None
        try:
            catalog_url = urlparse.urlparse(
                self.nova_client.client.management_url)
        except Exception as e:
            script_unknown("unknown error parsing the catalog url : %s" % e)

        port = endpoint_url.port
        if port is None:
            if catalog_url.port is None:
                port = DAEMON_DEFAULT_PORT
            else:
                port = catalog_url.port

        netloc = "%s:%i" % (endpoint_url.hostname, port)
        url = urlparse.urlunparse([scheme,
                                   netloc,
                                   catalog_url.path,
                                   catalog_url.params,
                                   catalog_url.query,
                                   catalog_url.fragment])
        self.nova_client.client.management_url = url

    def check_existing_volume(self, volume_name, delete):
        count = 0
        for s in self.nova_client.volumes.list():
            if s.display_name == volume_name:
                if delete:
                    # asynchronous call, we do not check that it worked
                    s.delete()
                count += 1
        if count > 0:
            if delete:
                self.notifications.append("Found '%s' present %d time(s)"
                                          % (volume_name, count))
            else:
                self.msgs.append("Found '%s' present %d time(s). "
                                 % (volume_name, count)
                                 + "Won't create test volume. "
                                 + "Please check and delete.")

    def create_volume(self, volume_name, size, availability_zone, volume_type):
        if not self.msgs:
            try:
                conf = {'display_name': volume_name,
                        'size': size}
                if volume_type:
                    conf['volume_type'] = volume_type
                if availability_zone:
                    conf['availability_zone'] = availability_zone
                self.volume = self.nova_client.volumes.create(**conf)
            except Exception as e:
                self.msgs.append("Cannot create the volume %s (%s)"
                                 % (args.volume_name, e))

    def volume_ready(self, timeout):
        if not self.msgs:
            timer = 0
            while self.volume.status != "available":
                if timer >= timeout:
                    self.msgs.append("Cannot create the volume.")
                    break
                time.sleep(1)
                timer += 1
                try:
                    self.volume.get()
                except Exception as e:
                    self.msgs.append("Problem getting the status of "
                                     + "the volume: %s" % e)
                    break

    def delete_volume(self):
        if not self.msgs or self.volume is not None:
            try:
                self.volume.delete()
            except Exception as e:
                self.msgs.append("Problem deleting the volume: %s" % e)

    def volume_deleted(self, timeout):
        deleted = False
        timer = 0
        while not deleted and not self.msgs:
            time.sleep(1)
            if timer >= timeout:
                self.msgs.append("Could not delete the volume within"
                                 + "%d seconds" % timer)
                break
            timer += 1
            try:
                self.volume.get()
            except exceptions.NotFound:
                deleted = True
            except Exception as e:
                self.msgs.append("Cannot delete the volume (%s)" % e)
                break


parser = argparse.ArgumentParser(
    description='Check an OpenStack Keystone server.')
parser.add_argument('--auth_url', metavar='URL', type=str,
                    default=os.getenv('OS_AUTH_URL'),
                    help='Keystone URL')

parser.add_argument('--username', metavar='username', type=str,
                    default=os.getenv('OS_USERNAME'),
                    help='username to use for authentication')

parser.add_argument('--password', metavar='password', type=str,
                    default=os.getenv('OS_PASSWORD'),
                    help='password to use for authentication')

parser.add_argument('--tenant', metavar='tenant', type=str,
                    default=os.getenv('OS_TENANT_NAME'),
                    help='tenant name to use for authentication')

parser.add_argument('--endpoint_url', metavar='endpoint_url', type=str,
                    help='Override the catalog endpoint.')

parser.add_argument('--endpoint_type', metavar='endpoint_type', type=str,
                    default="publicURL",
                    help='Endpoint type in the catalog request. '
                    + 'Public by default.')

parser.add_argument('--force_delete', action='store_true',
                    help='If matching volumes are found, delete them and add '
                    + 'a notification in the message instead of getting out '
                    + 'in critical state.')


parser.add_argument('--api_version', metavar='api_version', type=str,
                    default='1',
                    help='Version of the API to use. 1 by default.')

parser.add_argument('--timeout', metavar='timeout', type=int,
                    default=120,
                    help='Max number of second to create/delete a volume '
                    + '(120 by default).')

parser.add_argument('--volume_name', metavar='volume_name', type=str,
                    default="monitoring_test",
                    help='Name of the volume to create '
                    + '(monitoring_test by default)')

parser.add_argument('--volume_size', metavar='volume_size', type=int,
                    default=1,
                    help='Size of the volume to create (1 GB by default)')

parser.add_argument('--volume_type', metavar='volume_type', type=str,
                    default=None,
                    help='With multiple backends, choose the volume type.')

parser.add_argument('--availability_zone', metavar='availability_zone',
                    type=str,
                    default=None,
                    help='Specify availability zone.')

parser.add_argument('--verbose', action='count',
                    help='Print requests on stderr.')

args = parser.parse_args()

# this shouldn't raise any exception as no connection is done when
# creating the object.  But It may change, so I catch everything.
try:
    nova_client = Client(args.api_version,
                         username=args.username,
                         project_id=args.tenant,
                         api_key=args.password,
                         auth_url=args.auth_url,
                         endpoint_type=args.endpoint_type,
                         http_log_debug=args.verbose)
except Exception as e:
    script_critical("Error creating cinder communication object: %s" % e)

util = Novautils(nova_client)

if args.verbose:
    ch = logging.StreamHandler()
    nova_client.client._logger.setLevel(logging.DEBUG)
    nova_client.client._logger.addHandler(ch)

# Initiate the first connection and catch error.
util.check_connection()

if args.endpoint_url:
    util.mangle_url(args.endpoint_url)
    # after mangling the url, the endpoint has changed.  Check that
    # it's valid.
    util.check_connection(force=True)

util.check_existing_volume(args.volume_name, args.force_delete)
util.create_volume(args.volume_name,
                   args.volume_size,
                   args.availability_zone,
                   args.volume_type)
util.volume_ready(args.timeout)
util.delete_volume()
util.volume_deleted(args.timeout)

if util.msgs:
    script_critical(", ".join(util.msgs))

duration = util.get_duration()
notification = ""

if util.notifications:
    notification = "(" + ", ".join(util.notifications) + ")"

print("OK - Volume spawned and deleted in %d seconds %s| time=%d"
      % (duration, notification, duration))
sys.exit(STATE_OK)
