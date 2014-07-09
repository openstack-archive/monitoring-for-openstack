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
# ## Requirements
# 
# * python
# * python-novaclient
# 
# ## Arguments
# 
# ### Optional arguments
# 
# * `-h`: Show the help message and exit
# * `--auth_url`: Keystone URL
# * `--username`: Username to use for authentication
# * `--password`: Password to use for authentication
# * `--tenant`: Tenant name to use for authentication
# * `--region_name`: Region to select for authentication
# * `--endpoint_url`: Override the catalog endpoint
# * `--endpoint_type`: When not overriding, which type to use in the catalog.  Public by default.
# * `--image_name`: Image name to use (cirros-0.3.0-x86_64-disk by defalut)
# * `--flavor_name`: Flavor name to use (m1.tiny by default)
# * `--instance_name`: Instance name to use (monitoring_test by default)
# * `--force_delete`: If matching instances are found delete them and add a notification in the message instead of getting out in critical state
# * `--api_version`: Version of the API to use. 2 by default. (1.1 supported, and 3 not tested)
# * `--timeout`: Max number of second to create/destroy a instance (120 by default).
# * `--verbose`: Print requests on stderr
# 
# ## Usage
# 
# * `check_nova-instance.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD --api_version '2' --instance_name 'test_from_api' --endpoint_url http://localhost`
# 
# For a asynchronous usage relative to a nagios check, one can use [cache_check.py](https://github.com/gaelL/nagios-cache-check)
# 
# * `cache_check.py -c "check_nova-instance.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD --api_version '2' --instance_name 'test_from_api3' --endpoint_url http://localhost" -e 150 -d -t 130 -i 180`
# 
# 
# ## Example.
# 
# I want to check every 30 minutes that the vm creation is working.  I
# estimate that about 3 minutes for the creation of a vm is too long.  I
# want to override the endpoint url return by the catalog to be able to
# specify one a the api server behind the load balancer.
# 
# So every 30 minutes nagios trigger this check:
# 
# * `cache_check.py -c "check_nova-instance.py --auth_url $OS_AUTH_URL --username $OS_USERNAME --tenant $OS_TENANT_NAME --password $OS_PASSWORD --api_version '2' --instance_name 'test_from_api3' --timeout 180 --endpoint_url http://localhost" -e 1920 -t 185 -i 1680`
# 
# * -e 1920 -t  185 -i 1680:
#     * the cache is expired when older than 32 minutes;
#     * command timeout about 3 minutes 5 secondes;
#     * the command won't be run more that once every 28 minutes (-i 1680);
# 

import sys
import argparse
from novaclient.client import Client
from novaclient import exceptions
import time
import logging
import urlparse
from datetime import datetime

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3

default_image_name = 'cirros-0.3.0-x86_64-disk'
default_flavor_name = 'm1.tiny'
default_instance_name = 'monitoring_test'


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
        self.notifications = ["instance_creation_time=%s" % self.start]
        self.performances = []
        self.instance = None
        self.connection_done = False

    def check_connection(self, force=False):
        if not self.connection_done or force:
            try:
                # force a connection to the server
                self.connection_done = self.nova_client.limits.get()
            except Exception as e:
                script_critical("Cannot connect to nova: %s\n" % e)

    def get_duration(self):
        return totimestamp() - self.start

    def mangle_url(self, url):
        self.check_connection()

        try:
            endpoint_url = urlparse.urlparse(url)
        except Exception as e:
            script_unknown("you must provide an endpoint_url in the form"
                           + "<scheme>://<url>/ (%s)\n" % e)
        scheme = endpoint_url.scheme
        if scheme is None:
            script_unknown("you must provide an endpoint_url in the form"
                           + "<scheme>://<url>/ (%s)\n" % e)
        catalog_url = None
        try:
            catalog_url = urlparse.urlparse(
                self.nova_client.client.management_url)
        except Exception as e:
            script_unknown("unknown error parsing the catalog url : %s\n" % e)

        port = endpoint_url.port
        if port is None:
            if catalog_url.port is None:
                port = 8774
            else:
                port = catalog_url.port

        netloc = "%s:%i" % (endpoint_url.hostname, port)
        url = urlparse.urlunparse([scheme,
                                   netloc,
                                   catalog_url.path,
                                   catalog_url.params,
                                   catalog_url.query,
                                   catalog_url.fragment])
        self.nova_client.client.set_management_url(url)

    def check_existing_instance(self, instance_name, delete, timeout=45):
        count = 0
        for s in self.nova_client.servers.list():
            if s.name == instance_name:
                if delete:
                    s.delete()
                    self._instance_status(s, timeout, count)
                    self.performances.append("undeleted_server_%s_%d=%s"
                                             % (s.name, count, s.created))
                count += 1
        if count > 0:
            if delete:
                self.notifications.append("Found '%s' present %d time(s)"
                                          % (instance_name, count))
            else:
                self.msgs.append(
                    "Found '%s' present %d time(s). " % (instance_name, count)
                    + "Won't create test instance. "
                    + "Please check and delete.")

    def get_image(self, image_name):
        if not self.msgs:
            try:
                self.image = self.nova_client.images.find(name=image_name)
            except Exception as e:
                self.msgs.append("Cannot find the image %s (%s)"
                                 % (image_name, e))

    def get_flavor(self, flavor_name):
        if not self.msgs:
            try:
                self.flavor = self.nova_client.flavors.find(name=flavor_name)
            except Exception as e:
                self.msgs.append("Cannot find the flavor %s (%s)"
                                 % (flavor_name, e))

    def create_instance(self, instance_name):
        if not self.msgs:
            try:
                self.instance = self.nova_client.servers.create(
                    name=instance_name,
                    image=self.image,
                    flavor=self.flavor)
            except Exception as e:
                self.msgs.append("Cannot create the vm %s (%s)"
                                 % (instance_name, e))

    def instance_ready(self, timeout):
        if not self.msgs:
            timer = 0
            while self.instance.status != "ACTIVE":
                if timer >= timeout:
                    self.msgs.append("Cannot create the vm")
                    break
                time.sleep(1)
                timer += 1
                try:
                    self.instance.get()
                except Exception as e:
                    self.msgs.append("Problem getting the status of the vm: %s"
                                     % e)
                    break

    def delete_instance(self):
        if not self.msgs or self.instance is not None:
            try:
                self.instance.delete()
            except Exception as e:
                self.msgs.append("Problem deleting the vm: %s" % e)

    def instance_deleted(self, timeout):
        deleted = False
        timer = 0
        while not deleted and not self.msgs:
            time.sleep(1)
            if timer >= timeout:
                self.msgs.append("Could not delete the vm within %d seconds"
                                 % timer)
                break
            timer += 1
            try:
                self.instance.get()
            except exceptions.NotFound:
                deleted = True
            except Exception as e:
                self.msgs.append("Cannot delete the vm (%s)" % e)
                break

    def _instance_status(self, instance, timeout, count):
        deleted = False
        timer = 0
        while not deleted:
            time.sleep(1)
            if timer >= timeout:
                self.msgs.append(
                    "Could not delete the vm %s within %d seconds "
                    % (instance.name, timer)
                    + "(created at %s)"
                    % instance.created)
                break
            timer += 1
            try:
                instance.get()
            except exceptions.NotFound:
                deleted = True
            except Exception as e:
                self.msgs.append("Cannot delete the vm %s (%s)"
                                 % (instance.name, e))
                self.performances.append("undeleted_server_%s_%d=%s"
                                         % (instance.name,
                                            count,
                                            instance.created))
                break


parser = argparse.ArgumentParser(
    description='Check an OpenStack Keystone server.')
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
                    help='Endpoint type in the catalog request.'
                    + 'Public by default.')

parser.add_argument('--image_name', metavar='image_name', type=str,
                    default=default_image_name,
                    help="Image name to use (%s by default)"
                    % default_image_name)

parser.add_argument('--flavor_name', metavar='flavor_name', type=str,
                    default=default_flavor_name,
                    help="Flavor name to use (%s by default)"
                    % default_flavor_name)

parser.add_argument('--instance_name', metavar='instance_name', type=str,
                    default=default_instance_name,
                    help="Instance name to use (%s by default)"
                    % default_instance_name)

parser.add_argument('--force_delete', action='store_true',
                    help='If matching instances are found delete them and add'
                    + 'a notification in the message instead of getting out'
                    + 'in critical state.')

parser.add_argument('--api_version', metavar='api_version', type=str,
                    default='2',
                    help='Version of the API to use. 2 by default.')

parser.add_argument('--timeout', metavar='timeout', type=int,
                    default=120,
                    help='Max number of second to create a instance'
                    + '(120 by default)')

parser.add_argument('--timeout_delete', metavar='timeout_delete', type=int,
                    default=45,
                    help='Max number of second to delete an existing instance'
                    + '(45 by default).')

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
    script_critical("Error creating nova communication object: %s\n" % e)

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

util.check_existing_instance(args.instance_name,
                             args.force_delete,
                             args.timeout_delete)
util.get_image(args.image_name)
util.get_flavor(args.flavor_name)
util.create_instance(args.instance_name)
util.instance_ready(args.timeout)
util.delete_instance()
util.instance_deleted(args.timeout)

if util.msgs:
    script_critical(", ".join(util.msgs))

duration = util.get_duration()
notification = ""
if util.notifications:
    notification = "(" + ", ".join(util.notifications) + ")"
performance = ""
if util.performances:
    performance = " ".join(util.performances)
print("OK - Nova instance spawned and deleted in %d seconds %s| time=%d %s"
      % (duration, notification, duration, performance))
sys.exit(STATE_OK)
