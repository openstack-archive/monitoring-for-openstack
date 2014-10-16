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

import json
import subprocess
import sys
import traceback


def per(percent, value):
    return percent / 100 * value


def remaning(avail, total):
    return "(%dMB/%dMB)" % (avail/1024, total/1024)


def interpret_output_df(output):
    '''Parse the output of ceph health.

    Return an exit code and message compatible with nagios.

    '''

    try:
        data = json.loads(output)
    except Exception:
        return (1, 'CEPH WARNING: unable to parse ceph df %s' %
                traceback.format_exc())

    warn_percent = int(sys.argv[1]) if len(sys.argv) >= 2 else 85
    crit_percent = int(sys.argv[2]) if len(sys.argv) >= 3 else 98

    total = int(data['stats']['total_space'])
    used = int(data['stats']['total_used'])
    avail = int(data['stats']['total_avail'])

    # Test correctness of values
    if used + avail != total:
        return (1, '[WARN] Used + Avail. != Total space')
    elif avail < per(crit_percent, total):
        return (2, "[ERR] Ceph df avail. critical %s" % remaning(avail, total))
    elif avail < per(warn_percent, total):
        return (1, "[WARN] Ceph df avail. waring %s" % remaning(avail, total))
    else:
        return (0, "[OK] Ceph df avail. seems good %s" %
                remaning(avail, total))


def check_ceph_df():
    'Program entry point.'

    try:
        res = subprocess.check_output(["ceph", "df", "--format=json"],
                                      stderr=subprocess.STDOUT)
        exit_code, message = interpret_output_df(res)
        sys.stdout.write("%s\n" % message)
        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        sys.stdout.write('CEPH UNKNOWN: %s\n' % e.output)
        sys.exit(3)
    except OSError:
        sys.stdout.write('CEPH UNKNOWN: unable to launch ceph health\n')
        sys.exit(3)


def interpret_output_health(output):
    '''Parse the output of ceph health.

    Return an exit code and message compatible with nagios.

    '''

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


def check_ceph_health():
    'Program entry point.'

    try:
        res = subprocess.check_output(["ceph", "health"],
                                      stderr=subprocess.STDOUT)
        exit_code, message = interpret_output_health(res)
        sys.stdout.write(message)
        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        sys.stdout.write('CEPH UNKNOWN: %s\n' % e.output)
        sys.exit(3)
    except OSError:
        sys.stdout.write('CEPH UNKNOWN: unable to launch ceph health\n')
        sys.exit(3)
