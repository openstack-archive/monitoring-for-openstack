#
# Copyright (C) 2014 eNovance SAS <licensing@enovance.com>
#
# Author: Frederic Lepied <frederic.lepied@enovance.com>
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

import unittest

from oschecks import ceph


class TestCephHealth(unittest.TestCase):

    def test_interpret_output_ok(self):
        exit_code, message = ceph.interpret_output_health('HEALTH_OK message')
        self.assertEqual(exit_code, 0)
        self.assertEqual(message, 'CEPH OK: message')

    def test_interpret_output_warn(self):
        exit_code, message = ceph.interpret_output_health('HEALTH_WARN '
                                                          'message')
        self.assertEqual(exit_code, 1)
        self.assertEqual(message, 'CEPH WARNING: message')

    def test_interpret_output_critical(self):
        exit_code, message = ceph.interpret_output_health('HEALTH_ERR message')
        self.assertEqual(exit_code, 2)
        self.assertEqual(message, 'CEPH CRITICAL: message')

    def test_interpret_output_unknown(self):
        exit_code, message = ceph.interpret_output_health('strange message')
        self.assertEqual(exit_code, 3)
        self.assertEqual(message, 'CEPH UNKNOWN: strange message')
