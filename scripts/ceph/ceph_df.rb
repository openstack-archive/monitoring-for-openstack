#!/usr/bin/env ruby
#
# Simple ceph df check (using ceph commands)
#
# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Sebastien Badia <sebastien.badia@enovance.com>
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
#

require 'rubygems' if RUBY_VERSION < '1.9.0'
require 'json'

# Monitoring return codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3
DEPENDENT = 4

warn_percent = ARGV[0] || 85
crit_percent = ARGV[1] || 98

begin
  data = JSON.load(`ceph df --format=json`)
rescue
  puts '[WARN] ceph not found ?'
  exit WARNING
end

total = data['stats']['total_space']
used = data['stats']['total_used']
avail = data['stats']['total_avail']

def per(percent,value)
  return (percent.to_f / 100) * value
end # def:: per(percent,value)

def remaning(avail,total)
  return "(#{avail/1024}MB/#{total/1024}MB)"
end # def:: avail

# Test correctness of values
if ( used + avail ) != total
  puts '[ERR] Used + Avail. != Total space'
  exit WARNING
end

if (avail >= per(crit_percent,total))
  puts "[ERR] Ceph df avail. critical #{remaning(avail,total)}"
  exit CRITICAL
elsif (avail >= per(warn_percent,total))
  puts "[WARN] Ceph df avail. warning #{remaning(avail,total)}"
  exit WARNING
else
  puts "[OK] Ceph df avail. seems good #{remaning(avail,total)}"
  exit OK
end
