#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# Openstack Monitoring script for Sensu / Nagios
#
# Copyright © 2013-2014 eNovance <licensing@enovance.com>
#
# Authors: Mehdi Abaakouk <mehdi.abaakouk@enovance.com>
#          Sofer Athlan-Guyot <sofer.athlan@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import argparse
import datetime
import logging
import os
import re
import urlparse

from keystoneclient.v2_0 import client
from neutronclient.neutron import client as neutron

from oschecks import utils


def _check_neutron_api():
    neutron = utils.Neutron()
    neutron.add_argument('-w', dest='warning', type=int, default=5,
                         help='Warning timeout for neutron APIs calls')
    neutron.add_argument('-c', dest='critical', type=int, default=10,
                         help='Critical timeout for neutron APIs calls')
    options, args, client = neutron.setup()

    elapsed, networks = utils.timeit(client.list_networks)
    if not networks or len(networks.get('networks', [])) <= 0:
        utils.critical("Unable to contact neutron API.")

    if elapsed > options.critical:
        utils.critical("Get networks took more than %d seconds, "
                       "it's too long.|response_time=%d" %
                       (options.critical, elapsed))
    elif elapsed > options.warning:
        utils.warning("Get networks took more than %d seconds, "
                      "it's too long.|response_time=%d" %
                      (options.warning, elapsed))
    else:
        utils.ok("Get networks, neutron API is working: "
                 "list %d networks in %d seconds.|response_time=%d" %
                 (len(networks['networks']), elapsed, elapsed))


def check_neutron_api():
    utils.safe_run(_check_neutron_api)


DAEMON_DEFAULT_PORT = 9696


def mangle_url(orig_url, url):
    try:
        endpoint_url = urlparse.urlparse(url)
    except Exception as e:
        utils.unknown("you must provide an endpoint_url in the form"
                      + "<scheme>://<url>/ (%s)\n" % e)
    scheme = endpoint_url.scheme
    if scheme is None:
        utils.unknown("you must provide an endpoint_url in the form"
                      + "<scheme>://<url>/ (%s)\n" % e)
    catalog_url = urlparse.urlparse(orig_url)

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
    return url


class Novautils(object):
    def __init__(self, nova_client, tenant_id):
        self.nova_client = nova_client
        self.msgs = []
        self.start = self.totimestamp()
        self.notifications = ["floatingip_creation_time=%s" % self.start]
        self.connection_done = False
        self.all_floating_ips = []
        self.fip = None
        self.network_id = None
        self.tenant_id = tenant_id

    # python has no "toepoch" method: http://bugs.python.org/issue2736
    # now, after checking http://stackoverflow.com/a/16307378,
    # and http://stackoverflow.com/a/8778548 made my mind to this approach
    @staticmethod
    def totimestamp(dt=None, epoch=datetime.datetime(1970, 1, 1)):
        if not dt:
            dt = datetime.datetime.utcnow()
        td = dt - epoch
        # return td.total_seconds()
        return int((td.microseconds + (td.seconds + td.days * 24 * 3600)
                    * 10**6) / 1e6)

    def check_connection(self, force=False):
        if not self.connection_done or force:
            try:
                # force a connection to the server
                self.connection_done = self.nova_client.list_ports()
            except Exception as e:
                utils.critical("Cannot connect to neutron: %s\n" % e)

    def get_duration(self):
        return self.totimestamp() - self.start

    def list_floating_ips(self):
        if not self.all_floating_ips:
            for floating_ip in self.nova_client.list_floatingips(
                    fields=['floating_ip_address', 'id'],
                    tenant_id=self.tenant_id)['floatingips']:
                self.all_floating_ips.append(floating_ip)
        return self.all_floating_ips

    def check_existing_floatingip(self, floating_ip=None, delete=False):
        count = 0
        found_ips = []
        for ip in self.list_floating_ips():
            if floating_ip == 'all' or floating_ip.match(
                    ip['floating_ip_address']):
                if delete:
                    # asynchronous call, we do not check that it worked
                    self.nova_client.delete_floatingip(ip['id'])
                found_ips.append(ip['floating_ip_address'])
                count += 1
        if count > 0:
            if delete:
                self.notifications.append("Found %d ip(s): %s"
                                          % (count, '{' + ', '.join(
                                             found_ips) + '}'))
            else:
                self.msgs.append("Found %d ip(s): %s. "
                                 % (count,  ', '.join(found_ips))
                                 + "Won't create test floating ip. "
                                 + "Please check and delete.")

    def get_network_id(self, router_name):
        if not self.msgs:
            if not self.network_id:
                try:
                    self.network_id = self.nova_client.list_networks(
                        name=router_name, fields='id')['networks'][0]['id']
                except Exception:
                    self.msgs.append("Cannot find ext router named '%s'."
                                     % router_name)

    def create_floating_ip(self):
        if not self.msgs:
            try:
                body = {'floatingip': {'floating_network_id': self.network_id}}
                self.fip = self.nova_client.create_floatingip(body=body)
                self.notifications.append(
                    "fip=%s" % self.fip['floatingip']['floating_ip_address'])
            except Exception as e:
                self.msgs.append("Cannot create a floating ip: %s" % e)

    def delete_floating_ip(self):
        if not self.msgs:
            try:
                self.nova_client.delete_floatingip(
                    self.fip['floatingip']['id'])
            except Exception:
                self.msgs.append("Cannot remove floating ip %s"
                                 % self.fip['floatingip']['id'])


def fip_type(string):
    if string == 'all':
        return 'all'
    else:
        return re.compile(string)


def _check_neutron_floating_ip():
    parser = argparse.ArgumentParser(
        description='Check an Floating ip creation. Note that it is able '
                    + 'to delete *all* floating ips from a account, so '
                    + 'ensure that nothing important is running on the '
                    + 'specified account.')
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
                        help='If matching floating ip are found, delete them '
                        + 'and add a notification in the message instead of '
                        + 'getting out in critical state.')

    parser.add_argument('--timeout', metavar='timeout', type=int,
                        default=120,
                        help='Max number of second to create/delete a '
                        + 'floating ip (120 by default).')

    parser.add_argument('--floating_ip', metavar='floating_ip', type=fip_type,
                        default=None,
                        help='Regex of IP(s) to check for existance. '
                        + 'This value can be "all" for conveniance (match '
                        + 'all ip). This permit to avoid certain floating '
                        + 'ip to be kept. Its default value prevents the '
                        + 'removal of any existing floating ip')

    parser.add_argument('--ext_router_name', metavar='ext_router_name',
                        type=str, default='public',
                        help='Name of the "public" router (public by default)')

    parser.add_argument('--verbose', action='count',
                        help='Print requests on stderr.')

    args = parser.parse_args()

    # this shouldn't raise any exception as no connection is done when
    # creating the object.  But It may change, so I catch everything.
    try:
        nova_client = client.Client(
            username=args.username,
            tenant_name=args.tenant,
            password=args.password,
            auth_url=args.auth_url,
        )
        nova_client.authenticate()
    except Exception as e:
        utils.critical("Authentication error: %s\n" % e)

    try:
        endpoint = nova_client.service_catalog.get_endpoints(
            'network')['network'][0][args.endpoint_type]
        if args.endpoint_url:
            endpoint = mangle_url(endpoint, args.endpoint_url)

        token = nova_client.service_catalog.get_token()['id']
        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)
        neutron_client = neutron.Client('2.0', endpoint_url=endpoint,
                                        token=token)

    except Exception as e:
        utils.critical("Error creating neutron object: %s\n" % e)
    util = Novautils(neutron_client, nova_client.tenant_id)

    # Initiate the first connection and catch error.
    util.check_connection()

    if args.floating_ip:
        util.check_existing_floatingip(args.floating_ip, args.force_delete)
    util.get_network_id(args.ext_router_name)
    util.create_floating_ip()
    util.delete_floating_ip()

    if util.msgs:
        utils.critical(", ".join(util.msgs))

    duration = util.get_duration()
    notification = ""

    if util.notifications:
        notification = "(" + ", ".join(util.notifications) + ")"

    utils.ok("Floating ip created and deleted %s| time=%d"
             % (notification, duration))


def check_neutron_floating_ip():
    utils.safe_run(_check_neutron_floating_ip)
