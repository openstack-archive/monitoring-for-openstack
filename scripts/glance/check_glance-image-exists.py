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


def check_glance():
    glance = utils.Glance()
    glance.add_argument('--req_count', dest='req_count', type=str,
                        required=False,
                        help='minimum number of images in glance')
    glance.add_argument('--req_images', metavar='req_images', type=str,
                        nargs='+', required=False,
                        help='name of images who must be available')
    options, args, client = glance.setup()

    #Flags resultat
    valid_image = 0
    count = 0
    if options.req_count:
        required_count = int(options.req_count)
        if (len(client.get_images(**{"limit": required_count}))
                >= required_count):
            count = 1

    if options.req_images:
        required_images = options.req_images
        for image in required_images:
            try:
                if len(client.get_images(**{"filters": {"name": image}})) == 1:
                    valid_image = valid_image + 1
            except:
                pass

    if options.req_count and count == 0:
        utils.critical("Failed - less than %d images found" % (required_count))

    if options.req_images and valid_image < len(required_images):
        utils.critical("Failed - '%s' %d/%d images found " %
                       (", ".join(required_images), valid_image,
                        len(required_images)))

    if options.req_images and options.req_count:
        utils.ok("image %s found and enough images >=%d" %
                 (", ".join(required_images), required_count))
    elif options.req_images:
        utils.ok("image %s found" % (", ".join(required_images)))
    elif options.req_count:
        utils.ok("more than %d images found" % (count))
    else:
        utils.ok("Connection glance established")


if __name__ == '__main__':
    utils.safe_run(check_glance)
