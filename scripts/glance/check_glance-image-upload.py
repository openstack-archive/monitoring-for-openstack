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


def check_glance_upload():
    glance = utils.Glance()
    glance.add_argument('--monitoring-image', dest='image_name', type=str,
                        default="openstack-monitoring-test-image",
                        help='Name of the monitoring image')
    options, args, client = glance.setup()

    data_raw = "X" * 1024 * 1024
    elapsed, res = utils.timeit(client.images.create,
                                data=data_raw,
                                disk_format='raw',
                                container_format='bare',
                                name=options.image_name)
    if not res or not res.id or res.status != 'active':
        utils.critical("Unable to upload image in Glance")

    res.delete()

    if elapsed > 20:
        utils.warning("Upload image in 20 seconds, it's too long")
    else:
        utils.ok("OK - Glance image uploaded in %s seconds" % elapsed)

if __name__ == '__main__':
    utils.safe_run(check_glance_upload)
