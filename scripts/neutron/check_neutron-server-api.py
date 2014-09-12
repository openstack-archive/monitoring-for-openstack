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

from oschecks import utils


def check_neutron_api():
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


if __name__ == '__main__':
    utils.safe_run(check_neutron_api)
