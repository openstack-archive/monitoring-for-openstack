#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# Openstack Monitoring script for Sensu / Nagios
#
# Copyright © 2013-2014 eNovance <licensing@enovance.com>
#
# Author: Mehdi Abaakouk <mehdi.abaakouk@enovance.com>
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
import time
import urlparse

from cinderclient.client import Client  # noqa
from cinderclient import exceptions

from oschecks import utils


def _check_cinder_api():
    cinder = utils.Cinder()
    cinder.add_argument('-w', dest='warning', type=int, default=5,
                        help='Warning timeout for cinder APIs calls')
    cinder.add_argument('-c', dest='critical', type=int, default=10,
                        help='Critical timeout for cinder APIs calls')
    options, args, client = cinder.setup()

    def quotas_list():
        return client.quotas.get(options.os_tenant_name)

    elapsed, quotas = utils.timeit(quotas_list)
    if not quotas:
        utils.critical("Unable to contact cinder API.")

    if elapsed > options.critical:
        utils.critical("Get quotas took more than %d seconds, "
                       "it's too long.|response_time=%d" %
                       (options.critical, elapsed))
    elif elapsed > options.warning:
        utils.warning("Get quotas took more than %d seconds, "
                      "it's too long.|response_time=%d" %
                      (options.warning, elapsed))
    else:
        utils.ok("Get quotas, cinder API is working: "
                 "list quota in %d seconds.|response_time=%d" %
                 (elapsed, elapsed))


def check_cinder_api():
    utils.safe_run(_check_cinder_api)


class Novautils(object):
    DAEMON_DEFAULT_PORT = 8776

    def __init__(self, nova_client):
        self.nova_client = nova_client
        self.msgs = []
        self.start = self.totimestamp()
        self.notifications = ["volume_creation_time=%s" % self.start]
        self.volume = None
        self.connection_done = False

    # python has no "toepoch" method: http://bugs.python.org/issue2736
    # now, after checking http://stackoverflow.com/a/16307378,
    # and http://stackoverflow.com/a/8778548 made my mind to this approach
    @staticmethod
    def totimestamp(dt=None, epoch=datetime.datetime(1970, 1, 1)):
        if not dt:
            dt = datetime.datetime.utcnow()
        td = dt - epoch
        # return td.total_seconds()
        return int((td.microseconds +
                   (td.seconds + td.days * 24 * 3600) * 10**6) / 1e6)

    def check_connection(self, force=False):
        if not self.connection_done or force:
            try:
                # force a connection to the server
                self.connection_done = self.nova_client.limits.get()
            except Exception as e:
                utils.critical("Cannot connect to cinder: %s" % e)

    def get_duration(self):
        return self.totimestamp() - self.start

    def mangle_url(self, url):
        # This first connection populate the structure we need inside
        # the object.  This does not cost anything if a connection has
        # already been made.
        self.check_connection()
        try:
            endpoint_url = urlparse.urlparse(url)
        except Exception as e:
            utils.unknown("you must provide an endpoint_url in the form"
                          + "<scheme>://<url>/ (%s)" % e)
        scheme = endpoint_url.scheme
        if scheme is None:
            utils.unknown("you must provide an endpoint_url in the form"
                          + "<scheme>://<url>/ (%s)" % e)
        catalog_url = None
        try:
            catalog_url = urlparse.urlparse(
                self.nova_client.client.management_url)
        except Exception as e:
            utils.unknown("unknown error parsing the catalog url : %s" % e)

        port = endpoint_url.port
        if port is None:
            if catalog_url.port is None:
                port = self.DAEMON_DEFAULT_PORT
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
                                 % (volume_name, e))

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


def _check_cinder_volume():
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
                        help='If matching volumes are found, delete them and '
                        + 'add a notification in the message instead of '
                        + 'getting out in critical state.')

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
        utils.critical("Error creating cinder communication object: %s" % e)

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
        utils.critical(", ".join(util.msgs))

    duration = util.get_duration()
    notification = ""

    if util.notifications:
        notification = "(" + ", ".join(util.notifications) + ")"

    utils.ok("Volume spawned and deleted in %d seconds %s| time=%d"
             % (duration, notification, duration))


def check_cinder_volume():
    utils.safe_run(_check_cinder_volume)
