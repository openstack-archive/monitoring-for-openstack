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
import sys

try:
    import utils
except ImportError:
    from oschecks import utils


def check_amqp():
    parser = argparse.ArgumentParser(
        description='Check amqp connection of an OpenStack service.')
    parser.add_argument('-n', dest='process_name',
                        help='Process name')
    options = parser.parse_args()
    if options.process_name:
        process_name = options.process_name
    else:
        process_name = os.path.basename(sys.argv[0])
        process_name = process_name.replace("check_amqp_", "")
        process_name = process_name.replace(".py", "")
    utils.check_process_exists_and_amqp_connected(process_name)

if __name__ == '__main__':
    utils.safe_run(check_amqp)
