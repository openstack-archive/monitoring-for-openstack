#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# Openstack Monitoring script for Sensu / Nagios
#
# Copyright © 2013-2014 eNovance <licensing@enovance.com>
#
# Author:Mehdi Abaakouk <mehdi.abaakouk@enovance.com>
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
import os
import shlex
import subprocess

try:
    import utils
except ImportError:
    from oschecks import utils


def _pacemaker_host_check():
    parser = argparse.ArgumentParser(
        description='Check amqp connection of an OpenStack service.')
    parser.add_argument('-r', dest='pacemaker_resource',
                        help='pacemaker resource', required=True)
    parser.add_argument('-s', dest='script', required=True,
                        help='Script')
    options = parser.parse_args()

    local_hostname = subprocess.check_output(['hostname', '-s']).strip()

    try:
        output = subprocess.check_output(['pcs', 'status'])
    except subprocess.CalledProcessError as e:
        utils.critical('pcs status with status %s: %s' %
                       e.returncode, e.output)
    except OSError:
        utils.critical('pcs not found')
    for line in output.splitlines():
        line = " ".join(line.strip().split())  # Sanitize separator
        if not line:
            continue

        resource, remaining = line.split(None, 1)
        if resource == options.pacemaker_resource:
            agent, __, remaining = remaining.partition(' ')
            if ' ' in remaining:
                status, __, current_hostname = remaining.partition(' ')
            else:
                status, current_hostname = remaining, ''
            if status != "Started":
                utils.critical("pacemaker resource %s is not started (%s)" %
                               (resource, status))
            if current_hostname != local_hostname:
                utils.ok("pacemaker resource %s doesn't on this node "
                         "(but on %s)" % (resource, current_hostname))
            script = shlex.split(options.script)
            os.execvp(script[0], script)

    else:
        utils.critical('pacemaker resource %s not found' %
                       options.pacemaker_resource)


def pacemaker_host_check():
    utils.safe_run(_pacemaker_host_check)
