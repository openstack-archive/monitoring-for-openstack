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


def check_nova_api():
    nova = utils.Nova()
    nova.add_argument('-w', dest='warning', type=int, default=5,
                        help='Warning timeout for nova APIs calls')
    nova.add_argument('-c', dest='critical', type=int, default=10,
                        help='Critical timeout for nova APIs calls')
    options, args, client = nova.setup()

    def flavors_list():
        return list(client.flavors.list())

    elapsed, flavors = utils.timeit(flavors_list)
    if not flavors:
        utils.critical("Unable to contact nova API.")

    if elapsed > options.critical:
        utils.critical("Get flavors took more than %d seconds, "
                       "it's too long.|response_time=%d" %
                       (options.critical, elapsed))
    elif elapsed > options.warning:
        utils.warning("Get flavors took more than %d seconds, "
                      "it's too long.|response_time=%d" %
                      (options.warning, elapsed))
    else:
        utils.ok("Get flavors, nova API is working: "
                 "list %d flavors in %d seconds.|response_time=%d" %
                 (len(flavors), elapsed, elapsed))


if __name__ == '__main__':
    utils.safe_run(check_nova_api)
