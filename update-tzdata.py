#!/usr/bin/python -B

# Copyright 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates the timezone data files used by Android."""

import ftplib
import glob
import httplib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.append('../../external/icu/tools')
import i18nutil
import tzdatautil
import updateicudata

regions = ['africa', 'antarctica', 'asia', 'australasia',
           'etcetera', 'europe', 'northamerica', 'southamerica',
           # These two deliberately come last so they override what came
           # before (and each other).
           'backward', 'backzone' ]

# Calculate the paths that are referred to by multiple functions.
android_build_top = i18nutil.GetAndroidRootOrDie()
timezone_dir = os.path.realpath('%s/system/timezone' % android_build_top)
i18nutil.CheckDirExists(timezone_dir, 'system/timezone')

zone_compactor_dir = os.path.realpath('%s/system/timezone/zone_compactor' % android_build_top)
i18nutil.CheckDirExists(timezone_dir, 'system/timezone/zone_zompactor')

timezone_input_data_dir = os.path.realpath('%s/input_data' % timezone_dir)

# TODO(nfuller): Move to {timezone_dir}/output_data. http://b/36882778
timezone_output_data_dir = '%s/output_data' % timezone_dir
i18nutil.CheckDirExists(timezone_output_data_dir, 'output_data')

tmp_dir = tempfile.mkdtemp('-tzdata')


def WriteSetupFile(extracted_iana_dir):
  """Writes the list of zones that ZoneCompactor should process."""
  links = []
  zones = []
  for region in regions:
    for line in open('%s/%s' % (extracted_iana_dir, region)):
      fields = line.split()
      if fields:
        if fields[0] == 'Link':
          links.append('%s %s %s' % (fields[0], fields[1], fields[2]))
          zones.append(fields[2])
        elif fields[0] == 'Zone':
          zones.append(fields[1])
  zones.sort()

  zone_compactor_setup_file = '%s/setup' % tmp_dir
  setup = open(zone_compactor_setup_file, 'w')
  for link in sorted(set(links)):
    setup.write('%s\n' % link)
  for zone in sorted(set(zones)):
    setup.write('%s\n' % zone)
  setup.close()
  return zone_compactor_setup_file


def BuildIcuData(iana_tar_file):
  icu_build_dir = '%s/icu' % tmp_dir

  updateicudata.PrepareIcuBuild(icu_build_dir)
  updateicudata.MakeTzDataFiles(icu_build_dir, iana_tar_file)
  updateicudata.MakeAndCopyIcuDataFiles(icu_build_dir)


def BuildTzdata(iana_tar_file):
  iana_tar_filename = os.path.basename(iana_tar_file)
  new_version = re.search('(tzdata.+)\\.tar\\.gz', iana_tar_filename).group(1)

  print 'Extracting...'
  extracted_iana_dir = '%s/extracted_iana' % tmp_dir
  os.mkdir(extracted_iana_dir)
  tar = tarfile.open(iana_tar_file, 'r')
  tar.extractall(extracted_iana_dir)

  print 'Calling zic(1)...'
  zic_output_dir = '%s/data' % tmp_dir
  os.mkdir(zic_output_dir)
  zic_generator_template = '%s/%%s' % extracted_iana_dir
  zic_inputs = [ zic_generator_template % x for x in regions ]
  zic_cmd = ['zic', '-d', zic_output_dir ]
  zic_cmd.extend(zic_inputs)
  subprocess.check_call(zic_cmd)

  zone_compactor_setup_file = WriteSetupFile(extracted_iana_dir)

  print 'Calling ZoneCompactor to update tzdata to %s...' % new_version
  class_files_dir = '%s/classes' % tmp_dir
  os.mkdir(class_files_dir)

  subprocess.check_call(['javac', '-d', class_files_dir,
                         '%s/main/java/ZoneCompactor.java' % zone_compactor_dir])

  zone_tab_file = '%s/zone.tab' % extracted_iana_dir

  iana_output_data_dir = '%s/iana' % timezone_output_data_dir
  subprocess.check_call(['java', '-cp', class_files_dir, 'ZoneCompactor',
                         zone_compactor_setup_file, zic_output_dir, zone_tab_file,
                         iana_output_data_dir, new_version])


def BuildTzlookup():
  # We currently just copy a manually-maintained xml file.
  tzlookup_source_file = '%s/android/tzlookup.xml' % timezone_input_data_dir
  tzlookup_dest_file = '%s/android/tzlookup.xml' % timezone_output_data_dir
  shutil.copyfile(tzlookup_source_file, tzlookup_dest_file)



# Run with no arguments from any directory, with no special setup required.
# See http://www.iana.org/time-zones/ for more about the source of this data.
def main():
  print 'Found source data file structure in %s ...' % timezone_input_data_dir

  iana_data_dir = '%s/iana' % timezone_input_data_dir
  iana_tar_file = tzdatautil.GetIanaTarFile(iana_data_dir)
  print 'Found IANA time zone data %s ...' % iana_tar_file

  print 'Found android output dir in %s ...' % timezone_output_data_dir
  print 'Found icu in %s ...' % updateicudata.icuDir()

  BuildIcuData(iana_tar_file)
  BuildTzdata(iana_tar_file)
  BuildTzlookup()
  print 'Look in %s and %s for new data files' % (timezone_output_data_dir, updateicudata.icuDir())
  sys.exit(0)


if __name__ == '__main__':
  main()
