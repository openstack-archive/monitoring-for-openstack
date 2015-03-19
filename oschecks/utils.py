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


import copy
import itertools
import os
import sys
import time
import traceback

import psutil

AMQP_PORT = 5672


def unknown(msg):
    print("UNKNOWN: %s" % msg)
    sys.exit(3)


def critical(msg):
    print("CRITICAL: %s" % msg)
    sys.exit(2)


def warning(msg):
    print("WARNING: %s" % msg)
    sys.exit(1)


def ok(msg):
    print("OK: %s" % msg)
    sys.exit(0)


def check_process_name(name, p):
    if p.name == name:
        return True
    # name can be truncated and a script so check also if it can be an
    # argument to an interpreter
    if len(p.cmdline) > 0 and os.path.basename(p.cmdline[0]) == name:
        return True
    if len(p.cmdline) > 1 and os.path.basename(p.cmdline[1]) == name:
        return True
    return False


def check_process_exists_and_amqp_connected(name):
    processes = filter(lambda p: check_process_name(name, p),
                       psutil.process_iter())
    if not processes:
        critical("%s is not running" % name)
    for p in processes:
        try:
            connections = p.get_connections(kind='inet')
        except psutil.NoSuchProcess:
            continue
        found_amqp = (
            len(list(itertools.takewhile(lambda c: len(c.remote_address) <= 1
                                         or c.remote_address[1]
                                         != AMQP_PORT, connections)))
            != len(connections))
        if found_amqp:
            ok("%s is working." % name)
    critical("%s is not connected to AMQP" % name)


def check_process_exists(name):
    processes = filter(lambda p: check_process_name(name, p),
                       psutil.process_iter())
    if not processes:
        critical("%s is not running" % name)
    ok("%s is working." % name)


def timeit_wrapper(func):
    def wrapper(*arg, **kw):
        t1 = time.time()
        res = func(*arg, **kw)
        t2 = time.time()
        return (t2 - t1), res
    return wrapper


@timeit_wrapper
def timeit(func, *args, **kwargs):
    return func(*args, **kwargs)


def safe_run(method):
    try:
        method()
    except Exception:
        critical(traceback.format_exc())


class Nova(object):
    def __init__(self):
        from novaclient import shell
        self.nova = shell.OpenStackComputeShell()
        self.base_argv = copy.deepcopy(sys.argv[1:])
        self.nova.parser = self.nova.get_base_parser()
        self.add_argument = self.nova.parser.add_argument

    def setup(self, api_version='1.1'):
        from novaclient import client
        (options, args) = self.nova.parser.parse_known_args(self.base_argv)
        if options.help:
            options.command = None
            self.nova.do_help(options)
            sys.exit(2)
        auth_token = None
        if options.os_auth_token and options.os_endpoint:
            auth_token = options.os_auth_token
        if options.os_compute_api_version:
            api_version = options.os_compute_api_version
        client = client.get_client_class(api_version)(
            options.os_username,
            options.os_password,
            options.os_tenant_name,
            tenant_id=options.os_tenant_id,
            auth_token=auth_token,
            auth_url=options.os_auth_url,
            region_name=options.os_region_name,
            cacert=options.os_cacert,
            insecure=options.insecure,
            timeout=options.timeout)
        return options, args, client


class Glance(object):
    def __init__(self):
        from glanceclient import shell
        self.glance = shell.OpenStackImagesShell()
        self.base_argv = copy.deepcopy(sys.argv[1:])
        self.glance.parser = self.glance.get_base_parser()
        self.add_argument = self.glance.parser.add_argument

    def setup(self, api_version=1):
        (options, args) = self.glance.parser.parse_known_args(self.base_argv)
        if options.help:
            options.command = None
            self.glance.do_help(options)
            sys.exit(2)
        client = self.glance._get_versioned_client(api_version, options,
                                                   force_auth=True)
        return options, args, client


class Ceilometer(object):
    def __init__(self):
        from ceilometerclient import shell
        self.ceilometer = shell.CeilometerShell()
        self.base_argv = copy.deepcopy(sys.argv[1:])
        # NOTE(gordc): workaround for bug1434264
        if not hasattr(self.ceilometer, 'auth_plugin'):
            from ceilometerclient import client
            if hasattr(client, 'AuthPlugin'):
                self.ceilometer.auth_plugin = client.AuthPlugin()
        self.ceilometer.parser = self.ceilometer.get_base_parser()
        self.add_argument = self.ceilometer.parser.add_argument

    def setup(self, api_version=2):
        from ceilometerclient import client
        (options, args) = self.ceilometer.parser.parse_known_args(
            self.base_argv)
        if options.help:
            options.command = None
            self.do_help(options)
            sys.exit(2)
        client_kwargs = vars(options)
        return options, client.get_client(api_version, **client_kwargs)


class Cinder(object):
    def __init__(self):
        from cinderclient import shell
        self.cinder = shell.OpenStackCinderShell()
        self.base_argv = copy.deepcopy(sys.argv[1:])
        self.cinder.parser = self.cinder.get_base_parser()
        self.add_argument = self.cinder.parser.add_argument

    def setup(self, api_version='1'):
        from cinderclient import client
        (options, args) = self.cinder.parser.parse_known_args(self.base_argv)
        if options.help:
            options.command = None
            self.cinder.do_help(options)
            sys.exit(2)
        if options.os_volume_api_version:
            api_version = options.os_volume_api_version
        client = client.get_client_class(api_version)(
            options.os_username,
            options.os_password,
            options.os_tenant_name,
            tenant_id=options.os_tenant_id,
            auth_url=options.os_auth_url,
            region_name=options.os_region_name,
            cacert=options.os_cacert,
            insecure=options.insecure)
        return options, args, client


class Neutron(object):
    def __init__(self):
        from neutronclient import shell
        self.neutron = shell.NeutronShell('2.0')
        self.base_argv = copy.deepcopy(sys.argv[1:])
        self.neutron.parser = self.neutron.build_option_parser(
            "Neutron client", "2.0")
        self.add_argument = self.neutron.parser.add_argument

    def setup(self):
        (options, args) = self.neutron.parser.parse_known_args(self.base_argv)
        self.neutron.options = options
        self.neutron.api_version = {'network': self.neutron.api_version}
        self.neutron.authenticate_user()
        return options, args, self.neutron.client_manager.neutron


class Keystone(object):
    def __init__(self):
        from keystoneclient import shell
        self.keystone = shell.OpenStackIdentityShell()
        self.base_argv = copy.deepcopy(sys.argv[1:])
        self.keystone.parser = self.keystone.get_base_parser()
        self.add_argument = self.keystone.parser.add_argument

    def setup(self, api_version="2.0"):
        (options, args) = self.keystone.parser.parse_known_args(self.base_argv)
        if options.help:
            self.keystone.do_help(options)
            sys.exit(2)
        self.keystone.auth_check(options)
        token = None
        if options.os_token and options.os_endpoint:
            token = options.os_token
        if options.os_identity_api_version:
            api_version = options.os_identity_api_version
        client = self.keystone.get_api_class(api_version)(
            username=options.os_username,
            tenant_name=options.os_tenant_name,
            tenant_id=options.os_tenant_id,
            token=token,
            endpoint=options.os_endpoint,
            password=options.os_password,
            auth_url=options.os_auth_url,
            region_name=options.os_region_name,
            cacert=options.os_cacert,
            key=options.os_key,
            cert=options.os_cert,
            insecure=options.insecure,
            debug=options.debug,
            use_keyring=options.os_cache,
            force_new_token=options.force_new_token,
            stale_duration=options.stale_duration,
            timeout=options.timeout)
        return options, args, client
