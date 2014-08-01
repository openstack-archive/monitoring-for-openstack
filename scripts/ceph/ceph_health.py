#!/usr/bin/env python
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

''' Nagios check using ceph health.
'''

import subprocess
import sys


def interpret_output(output):
    '''Parse the output of ceph health and return an exit code and
message compatible with nagios.'''
    tokens = output.split(' ')
    if len(tokens) == 1:
        tokens[0] = tokens[0].strip()
        tokens.append('\n')
    if tokens[0] == 'HEALTH_OK':
        return (0, 'CEPH OK: ' + ' '.join(tokens[1:]))
    elif tokens[0] == 'HEALTH_WARN':
        return (1, 'CEPH WARNING: ' + ' '.join(tokens[1:]))
    elif tokens[0] == 'HEALTH_ERR':
        return (2, 'CEPH CRITICAL: ' + ' '.join(tokens[1:]))
    else:
        return (3, 'CEPH UNKNOWN: ' + ' '.join(tokens))


def main():
    'Program entry point.'
    try:
        res = subprocess.check_output(["ceph", "health"],
                                      stderr=subprocess.STDOUT)
        exit_code, message = interpret_output(res)
        sys.stdout.write(message)
        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        sys.stdout.write('CEPH UNKNOWN: %s\n' % e.output)
        sys.exit(3)
    except OSError:
        sys.stdout.write('CEPH UNKNOWN: unable to launch ceph health\n')
        sys.exit(3)

if __name__ == "__main__":
    main()

# ceph_health.py ends here
