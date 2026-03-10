# If not stated otherwise in this file or this component's license file the
# following copyright and licenses apply:
#
# Copyright 2020 RDK Management
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# - Try to find Telemetry library
# Once done this will define
#  TELEMETRY_FOUND - System has Telemetry
#  TELEMETRY_LIBRARIES - The libraries needed to use Telemetry
#  TELEMETRY_INCLUDE_DIRS - The headers needed to use Telemetry

find_package(PkgConfig)

find_library(TELEMETRY_LIBRARIES NAMES telemetry_msgsender)
find_path(TELEMETRY_INCLUDE_DIRS NAMES telemetry_busmessage_sender.h)

include(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(TELEMETRY DEFAULT_MSG TELEMETRY_INCLUDE_DIRS TELEMETRY_LIBRARIES)

mark_as_advanced(
    TELEMETRY_FOUND
    TELEMETRY_INCLUDE_DIRS
    TELEMETRY_LIBRARIES)
