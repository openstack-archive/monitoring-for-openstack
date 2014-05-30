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
# Requirments: python-keystoneclient, python-argparse, python

import sys
import argparse
from cinderclient.client import Client
#from novaclient.client import Client
from cinderclient import exceptions
import time
import logging
import urlparse
from datetime import datetime

DAEMON_DEFAULT_PORT=8776

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3

def script_error(msg):
    sys.stderr.write("UNKNOWN - %s" % msg)
    sys.exit(STATE_UNKNOWN)

class Novautils:
    def __init__(self, nova_client):
        self.nova_client = nova_client
        self.msgs = []
        self.volume = None
        self.start = datetime.now()

    def get_duration(self):
        return (datetime.now() - self.start).seconds

    def mangle_url(self, url):
        # need to populate management_url property
        try:
            self.nova_client.volumes.list()
        except Exception as e:
            script_error("unknown error filling object with data: %s\n" % e)


        import pdb; pdb.set_trace()

        try:
            endpoint_url = urlparse.urlparse(url)
        except Exception as e:
            script_error("you must provide an endpoint_url in the form <scheme>://<url>/ (%s)\n" % e)
        scheme = endpoint_url.scheme
        if scheme is None:
            script_error("you must provide an endpoint_url in the form <scheme>://<url>/ (%s)\n" % e)
        catalog_url = None
        try:
            catalog_url = urlparse.urlparse(self.nova_client.client.management_url)
        except Exception as e:
            script_error("unknown error parsing the catalog url : %s\n" % e)

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

    def check_existing_volume(self, volume_name):
        count = 0
        for s in self.nova_client.volumes.list():
            if s.display_name == volume_name:
                count += 1
        if count > 0:
            self.msgs.append("Found '%s' present %d time(s).  Won't create test volume.  Please check and delete." % (volume_name, count))

    def create_volume(self, volume_name, size):
        if not self.msgs:
            try:
                self.volume = self.nova_client.volumes.create(display_name=volume_name,
                                                             size=size)
            except Exception as e:
                self.msgs.append("Cannot create the vm %s (%s)" % (args.volume_name, e))

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
                    self.msgs.append("Problem getting the status of the volume: %s" % e)
                    break

    def delete_volume(self):
        if not self.msgs or self.volume != None:
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
                self.msgs.append("Could not delete the volume within %d seconds" % timer)
                break
            timer += 1
            try:
                self.volume.get()
            except exceptions.NotFound:
                deleted = True
            except Exception as e:
                self.msgs.append("Cannot delete the volume (%s)" % e)
                break


parser = argparse.ArgumentParser(description='Check an OpenStack Keystone server.')
parser.add_argument('--auth_url', metavar='URL', type=str,
                    required=True,
                    help='Keystone URL')

parser.add_argument('--username', metavar='username', type=str,
                    required=True,
                    help='username to use for authentication')

parser.add_argument('--password', metavar='password', type=str,
                    required=True,
                    help='password to use for authentication')

parser.add_argument('--tenant', metavar='tenant', type=str,
                    required=True,
                    help='tenant name to use for authentication')

parser.add_argument('--endpoint_url', metavar='endpoint_url', type=str,
                    help='Override the catalog endpoint.')

parser.add_argument('--endpoint_type', metavar='endpoint_type', type=str,
                    default="publicURL",
                    help='Endpoint type in the catalog request.  Public by default.')

parser.add_argument('--api_version', metavar='api_version', type=str,
                    default='1',
                    help='Version of the API to use. 2 by default.')

parser.add_argument('--timeout', metavar='timeout', type=int,
                    default=120,
                    help='Max number of second to create a vm (120 by default).')

parser.add_argument('--volume_name', metavar='volume_name', type=str,
                    default="monitoring_test",
                    help='Name of the volume to create')

parser.add_argument('--volume_size', metavar='volume_size', type=int,
                    default=1,
                    help='Size of the volume to create')

parser.add_argument('--verbose', action='count',
                    help='Print requests on stderr.')

args = parser.parse_args()
nova_client = Client(args.api_version,
                     username=args.username,
                     project_id=args.tenant,
                     api_key=args.password,
                     auth_url=args.auth_url,
                     endpoint_type=args.endpoint_type,
                     http_log_debug=args.verbose)

util = Novautils(nova_client)

if args.verbose:
    ch = logging.StreamHandler()
    nova_client.client._logger.setLevel(logging.DEBUG)
    nova_client.client._logger.addHandler(ch)

if args.endpoint_url:
    util.mangle_url(args.endpoint_url)

util.check_existing_volume(args.volume_name)
util.create_volume(args.volume_name,args.volume_size)
util.volume_ready(args.timeout)
util.delete_volume()
util.volume_deleted(args.timeout)

if util.msgs:
    print "CRITICAL - %s" % ", ".join(util.msgs)
    sys.exit(STATE_CRITICAL)

duration = util.get_duration()    
print("OK - Volume spawned and deleted in %d seconds | time=%d" % (duration, duration))
sys.exit(STATE_OK)
