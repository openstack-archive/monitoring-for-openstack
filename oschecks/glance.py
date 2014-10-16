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

from oschecks import utils


def _check_glance_api():
    glance = utils.Glance()
    glance.add_argument('-w', dest='warning', type=int, default=5,
                        help='Warning timeout for Glance APIs calls')
    glance.add_argument('-c', dest='critical', type=int, default=10,
                        help='Critical timeout for Glance APIs calls')
    options, args, client = glance.setup()

    def images_list():
        return list(client.images.list())

    elapsed, images = utils.timeit(images_list)
    if not images:
        utils.critical("Unable to contact Glance API.")

    if elapsed > options.critical:
        utils.critical("Get images took more than %d seconds, "
                       "it's too long.|response_time=%d" %
                       (options.critical, elapsed))
    elif elapsed > options.warning:
        utils.warning("Get images took more than %d seconds, "
                      "it's too long.|response_time=%d" %
                      (options.warning, elapsed))
    else:
        utils.ok("Get images, Glance API is working: "
                 "list %d images in %d seconds.|response_time=%d" %
                 (len(images), elapsed, elapsed))


def check_glance_api():
    utils.safe_run(_check_glance_api)


def _check_glance_image_exists():
    glance = utils.Glance()
    glance.add_argument('--req_count', dest='req_count', type=int,
                        required=False, default=0,
                        help='minimum number of images in glance')
    glance.add_argument('--req_images', metavar='req_images', type=str,
                        nargs='+', required=False,
                        help='name of images who must be available')
    options, args, client = glance.setup()

    # Flags resultat
    valid_image = 0
    count = len(list(client.images.list(**{"limit": options.req_count or 1})))

    if options.req_images:
        required_images = options.req_images
        for image in required_images:
            try:
                if len(list(client.images.list(
                        **{"filters": {"name": image}}))) == 1:
                    valid_image = valid_image + 1
            except Exception:
                pass

    if options.req_count and count < options.req_count:
        utils.critical("Failed - less than %d images found (%d)" %
                       (options.req_count, count))

    if options.req_images and valid_image < len(required_images):
        utils.critical("Failed - '%s' %d/%d images found " %
                       (", ".join(required_images), valid_image,
                        len(required_images)))

    if options.req_images and options.req_count:
        utils.ok("image %s found and enough images >=%d" %
                 (", ".join(required_images), options.req_count))
    elif options.req_images:
        utils.ok("image %s found" % (", ".join(required_images)))
    elif options.req_count:
        utils.ok("more than %d images found" % (count))
    else:
        utils.ok("Connection glance established")


def check_glance_image_exists():
    utils.safe_run(_check_glance_image_exists)


def _check_glance_upload():
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
        utils.ok("Glance image uploaded in %s seconds" % elapsed)


def check_glance_upload():
    utils.safe_run(_check_glance_upload)
