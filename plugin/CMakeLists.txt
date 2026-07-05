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
set(PLUGIN_NAME HdmiCecSink)
set(MODULE_NAME ${NAMESPACE}${PLUGIN_NAME})
set(PLUGIN_IMPLEMENTATION ${MODULE_NAME}Implementation)


set(PLUGIN_HDMICECSINK_STARTUPORDER "" CACHE STRING "To configure startup order of HdmiCecSink plugin")

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

find_package(${NAMESPACE}Plugins REQUIRED)
find_package(${NAMESPACE}Helpers REQUIRED)

add_library(${MODULE_NAME} SHARED
        HdmiCecSink.cpp
        Module.cpp)

# ── DeviceSettings plugin COM-RPC integration ─────────────────────────────────
# Selects DS_COMRPC/ (USE_DEVICESETTING_PLUGIN=ON) or DS_IARM/ (OFF) for the
# plugin implementation, so no #ifdef USE_DEVICESETTING_PLUGIN in any .cpp/.h.
# ──────────────────────────────────────────────────────────────────────────────
option(USE_DEVICESETTING_PLUGIN
    "Enable COM-RPC integration with entservices-devicesettings for HdmiCecSink (replaces libds/IARM path)"
    ON)

if (USE_DEVICESETTING_PLUGIN)
    # ── DS_COMRPC/ path ───────────────────────────────────────────────────────
    # Uses IDeviceSettingsHDMIIn COM-RPC. Does NOT link libds.so.
    set(HDMICECSINK_IMPL_SRC DS_COMRPC/HdmiCecSinkImplementation.cpp)
    set(HDMICECSINK_IMPL_INC ${CMAKE_CURRENT_SOURCE_DIR}/DS_COMRPC)
    message(STATUS "HdmiCecSink: USE_DEVICESETTING_PLUGIN=ON — DS_COMRPC/ path (no libds)")
else()
    # ── DS_IARM/ path ─────────────────────────────────────────────────────────
    # Uses device:: libds APIs directly via IARM bus.
    set(HDMICECSINK_IMPL_SRC DS_IARM/HdmiCecSinkImplementation.cpp)
    set(HDMICECSINK_IMPL_INC ${CMAKE_CURRENT_SOURCE_DIR}/DS_IARM)
    message(STATUS "HdmiCecSink: USE_DEVICESETTING_PLUGIN=OFF — DS_IARM/ path (libds/IARM)")
endif()

add_library(${PLUGIN_IMPLEMENTATION} SHARED
        ${HDMICECSINK_IMPL_SRC}
        Module.cpp)

set_target_properties(${MODULE_NAME} PROPERTIES
        CXX_STANDARD 11
        CXX_STANDARD_REQUIRED YES)

set_target_properties(${PLUGIN_IMPLEMENTATION} PROPERTIES
        CXX_STANDARD 11
        CXX_STANDARD_REQUIRED YES)

target_compile_definitions(${MODULE_NAME} PRIVATE MODULE_NAME=Plugin_${PLUGIN_NAME})

find_package(DS)
find_package(IARMBus)
find_package(CEC)
find_package(Telemetry)

target_include_directories(${MODULE_NAME} PRIVATE ${IARMBUS_INCLUDE_DIRS})
target_include_directories(${MODULE_NAME} PRIVATE ${CEC_INCLUDE_DIRS})
target_include_directories(${MODULE_NAME} PRIVATE ${DS_INCLUDE_DIRS})
set_source_files_properties(HdmiCecSink.cpp PROPERTIES COMPILE_FLAGS "-fexceptions")

target_include_directories(${PLUGIN_IMPLEMENTATION} PRIVATE
        ${IARMBUS_INCLUDE_DIRS}
        ${CEC_INCLUDE_DIRS}
        ${HDMICECSINK_IMPL_INC})
set_source_files_properties(${HDMICECSINK_IMPL_SRC} PROPERTIES COMPILE_FLAGS "-fexceptions")

if (USE_DEVICESETTING_PLUGIN)
    find_package(${NAMESPACE}Definitions REQUIRED)
    target_compile_definitions(${PLUGIN_IMPLEMENTATION} PRIVATE USE_DEVICESETTING_PLUGIN)
    target_link_libraries(${PLUGIN_IMPLEMENTATION} PUBLIC
            ${NAMESPACE}Plugins::${NAMESPACE}Plugins
            ${IARMBUS_LIBRARIES}
            ${CEC_LIBRARIES}
            ${NAMESPACE}Definitions::${NAMESPACE}Definitions
            ${NAMESPACE}::${NAMESPACE}Helpers)
else()
    target_include_directories(${PLUGIN_IMPLEMENTATION} PRIVATE ${DS_INCLUDE_DIRS})
    target_link_libraries(${PLUGIN_IMPLEMENTATION} PUBLIC
            ${NAMESPACE}Plugins::${NAMESPACE}Plugins
            ${IARMBUS_LIBRARIES}
            ${CEC_LIBRARIES}
            ${DS_LIBRARIES}
            ${NAMESPACE}::${NAMESPACE}Helpers)
endif()

target_link_libraries(${MODULE_NAME} PUBLIC
        ${NAMESPACE}Plugins::${NAMESPACE}Plugins
        ${IARMBUS_LIBRARIES}
        ${CEC_LIBRARIES}
        ${DS_LIBRARIES}
        ${NAMESPACE}::${NAMESPACE}Helpers)

if (NOT RDK_SERVICES_L1_TEST)
    target_compile_options(${PLUGIN_IMPLEMENTATION} PRIVATE -Wno-error=deprecated)
endif ()

if (RDK_SERVICE_L2_TEST)
   find_library(TESTMOCKLIB_LIBRARIES NAMES TestMocklib)
   if (TESTMOCKLIB_LIBRARIES)
       message ("linking mock libraries ${TESTMOCKLIB_LIBRARIES} library")
       target_link_libraries(${PLUGIN_IMPLEMENTATION} PRIVATE ${TESTMOCKLIB_LIBRARIES})
   else (TESTMOCKLIB_LIBRARIES)
       message ("Require ${TESTMOCKLIB_LIBRARIES} library")
   endif (TESTMOCKLIB_LIBRARIES)
endif (RDK_SERVICES_L2_TEST)

if(TELEMETRY_FOUND)
    target_link_libraries(${MODULE_NAME} PRIVATE ${TELEMETRY_LIBRARIES})
    target_include_directories(${MODULE_NAME} PRIVATE ${TELEMETRY_INCLUDE_DIRS})
    target_link_libraries(${PLUGIN_IMPLEMENTATION} PRIVATE ${TELEMETRY_LIBRARIES})
    target_include_directories(${PLUGIN_IMPLEMENTATION} PRIVATE ${TELEMETRY_INCLUDE_DIRS})
endif()

install(TARGETS ${MODULE_NAME}
        DESTINATION lib/${STORAGE_DIRECTORY}/plugins)

install(TARGETS ${PLUGIN_IMPLEMENTATION}
        DESTINATION lib/${STORAGE_DIRECTORY}/plugins)

write_config(${PLUGIN_NAME})
