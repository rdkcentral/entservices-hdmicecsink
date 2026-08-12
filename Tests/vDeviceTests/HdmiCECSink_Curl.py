"""
/**
 * @file HdmiCECSink_Curl.py
 * @brief Provides reusable curl argv commands for HDMI-CEC Sink JSON-RPC APIs.
 *
 * @testcase HdmiCECSink_Curl
 * @details Defines deterministic argv command lists consumed by the HDMI-CEC Sink
 *          device-level test cases. Each constant is a list of already-separated
 *          arguments, executed without a shell by utils.send_curl_command, so no quote,
 *          semicolon or $(...) inside a JSON payload or an endpoint is ever interpreted
 *          (CWE-78). Where an API is exercised both with accepted and with rejected
 *          arguments, the two are separate constants - set_vendor_id beside
 *          set_vendor_id_invalid, for instance. This module authors commands for external
 *          execution and does not start or emulate their required services.
 *
 *          The constants are INERT DATA, never shell input. utils.send_curl_command
 *          takes whichever constant it is given as an argv list and executes it in a
 *          bounded subprocess with no shell, so the WPEFRAMEWORK_JSONRPC_URL appended below -
 *          which comes from the environment - is passed to curl as a single argument and
 *          can never be interpreted as shell syntax. utils.py additionally rejects any
 *          endpoint override carrying whitespace or a shell metacharacter before
 *          publishing it. Do not reintroduce os.popen, os.system or shell=True for these
 *          strings, and do not build a command line from them by concatenation.
 *
 *          THE "--" BEFORE EVERY URL IS LOAD-BEARING, NOT DECORATION. curl reads any
 *          argument beginning with "-" as an OPTION, so an endpoint is only guaranteed to
 *          be read as an operand when the option terminator precedes it. Every constant
 *          below therefore carries "--" as its second-to-last element, immediately before
 *          WPEFRAMEWORK_JSONRPC_URL. utils._run_curl inserts the same terminator into any
 *          argv that reaches it without one, so the guarantee holds for the whole suite
 *          rather than only for the lists in this file - but keep it here as well, because
 *          a definition that carries its own terminator states the intent where the reader
 *          of the definition can see it. When adding a constant, place "--" last but one.
 *
 * @precondition
 *  - utils.py resolves WPEFRAMEWORK_JSONRPC_URL to a reachable WPEFramework endpoint.
 *  - The device under test hosts an active org.rdk.HdmiCecSink plugin when a command is
 *    dispatched.
 *
 * @dependencies
 *  - utils.py supplies the shared WPEFRAMEWORK_JSONRPC_URL endpoint and the shell-free
 *    send_curl_command dispatcher that executes these constants as argv lists. It is the
 *    only module this one imports, and the only one it needs.
 *  - The consumers of these constants are all present in this directory: every one of the
 *    33 Testcases/TCID*.py modules imports this module for its command strings, and so
 *    does Init_Devicelist_Populate.py (as HdmiCecSinkApis) for suite initialisation.
 *    SuitManager.py declares it as a suite dependency and loads those cases.
 *
 * @expected_result
 *  - Importers receive well-formed curl argv lists for the sink JSON-RPC APIs.
 *
 * @pass_criteria
 *  - Each constant preserves its specified method, payload, timeout, and shared URL,
 *    with one argument per list element, the "--" option terminator last but one, and
 *    the endpoint last.
 *
 * @failure_criteria
 *  - A definition names the wrong method, carries the wrong payload, or its consuming test
 *    dispatches it without the required device-level prerequisites.
 */
"""

from utils import WPEFRAMEWORK_JSONRPC_URL


get_active_route = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getActiveRoute"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_active_source = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getActiveSource"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_audio_device_connected_status = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_device_list = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getDeviceList"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_enabled = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getEnabled"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_osd_name = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getOSDName"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


get_vendor_id = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.getVendorId"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


# THERE IS NO getCecVersion CONSTANT HERE, AND THAT IS THE POINT.
#
# `org.rdk.HdmiCecSink.getCecVersion` is not a registered JSON-RPC method, so a command constant
# for it would be a capability this suite does not have. Four independent confirmations, kept
# because they are what the absence rests on:
#   1. it is absent from the generated registration list in the built
#      interfaces/json/JHdmiCecSink.h (a grep for it returns no hits);
#   2. it is absent from the `handler.Exists` assertions in the sink L1 RegisteredMethods test;
#   3. HdmiCecSinkImplementation::getCecVersion() is a private void internal helper called only
#      from Configure() -- it neither returns a value to a caller nor is wired to the JSON-RPC
#      surface;
#   4. a workspace-wide grep for _T("getCecVersion") finds only the sink L1 test file, where two
#      ENABLED and passing cases assert the same absence from the two entry points the dispatcher
#      offers: HdmiCecSinkInitializedEventDsTest.getCecVersion asserts the INVOKE-level refusal
#      (ERROR_UNKNOWN_KEY, i.e. 22, and an empty response body), and HdmiCecSinkDsTest
#      .cecVersionIsNotAPublishedMethodButIsObservableThroughTheDeviceList asserts the EXISTS-level
#      refusal - each with a getDeviceList control beside it so a broken dispatcher cannot make the
#      negative pass vacuously.  The first of those two was DISABLED until the QA-remediation pass:
#      it expected the read-back {"CECVersion":"1.4","success":true}, which cannot happen, so its
#      assertions were narrowed to the refusal that does happen and the case was enabled.
# The mechanism behind all four: the method is absent from IHdmiCecSink.h's published set and
# therefore from Exchange::JHdmiCecSink::Register, which is the plugin's only JSON-RPC
# registration path. Publishing it is a production change - a declaration on
# Exchange::IHdmiCecSink so ThunderTools generates the binding, plus a plugin implementation -
# which AAP Directive 6 requires be reported rather than made.
#
# Where the CEC version IS observable, and what TCID05_Get_CEC_Version exercises instead: a
# DIRECTED <Get CEC Version> (Device_Get_CEC_Version.yaml) drives the sink's own responder in
# HdmiCecSinkProcessor::process(const GetCECVersion &, const Header &), a DIRECTED <CEC Version>
# from a peer (Device_CEC_Version.yaml) is recorded by process(const CECVersion &, const Header &)
# into that peer's device-list entry, and `get_device_list` above reads it back as the entry's
# "cecVersion". If the plugin ever publishes the method, add a `get_cec_version` constant here
# alongside the others and restore the original read-back assertion in
# HdmiCecSinkInitializedEventDsTest.getCecVersion (../L1Tests/tests/test_HdmiCecSink.cpp), which
# currently asserts the refusal instead and will fail the moment the method appears.


print_device_list = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.printDeviceList"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


request_active_source = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.requestActiveSource"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


request_short_audio_descriptor = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.requestShortAudioDescriptor"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


request_audio_device_power_status = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.requestAudioDevicePowerStatus"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


send_audio_device_power_on_message = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendAudioDevicePowerOnMessage"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


send_get_audio_status_message = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendGetAudioStatusMessage"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


send_standby_message = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendStandbyMessage"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_active_source = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setActiveSource"}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


# The three key-control commands below address logical address 5, the Audio System.
#
# ADDRESS 5 IS A PEER OF THE DEVICE UNDER TEST, NOT THE DEVICE UNDER TEST. The emulated device is
# the television VTV: vcomponent_configurations/hdmicec/hdmicec_vcomponent_configuration.yaml and
# the config.emulated_device block of vcomponent_configurations/commands/
# Device_Config_Add_Network.yaml both declare name "VTV" with device_type "TV", and that is a HAL
# requirement rather than a preference - HdmiCecAddLogicalAddress refuses the request outright
# unless the emulated device is a TV AND the address is 0 (vcHdmiCec.c:845-849), so a DUT declared
# as anything else could neither claim an address nor transmit a frame. The audio system is the
# child peer YAMAHA, declared in the same network document beneath VTV at physical address
# 2.0.0.0, and the vComponent offers an audio system exactly one logical address -
# LOGICAL_ADDRESS_AUDIOSYSTEM == 5 (vcCommand.h:199, the single candidate in
# vcDevice_AllocateLogicalAddress) - so 5 is fixed rather than chosen. The authoritative statement
# of all of this is the header of hdmicec_vcomponent_configuration.yaml, which names this module
# as one of the four documents that move together with it.
#
# Two properties of that peer are why every key-control command here targets it rather than
# another one, and both are properties of address 5 specifically:
#
#   * Its registration is separately observable. HdmiCecSinkImplementation::addDevice() raises
#     ReportAudioDeviceConnectedStatus only under `if(logicalAddress == 0x5)`
#     (HdmiCecSinkImplementation.cpp:2456-2462); every other address gets OnDeviceAdded alone.
#   * It is the only initiator the sink's ARC gate accepts. process(InitiateArc) and
#     process(TerminateArc) both open with `if((!(header.from.toInt() == 0x5)) || (header.to ==
#     BROADCAST)) return;` (:510-513 and :537-540), so the ARC flows in TCID20 and TCID21 are
#     bound to this address too. Keeping the key-control commands on it means one peer's state is
#     what every one of those cases reads.
#
# The other five addresses ARE occupied, and a command sent to one of them also reaches a real
# peer: Device_Config_Add_Network.yaml declares DENON, LG, SAMSUNG, SONY and PANASONIC alongside
# YAMAHA, and the emulator allocates all six logical addresses - 1, 2, 3, 4, 5 and 8 - when that
# document is posted, which Init_Devicelist_Populate.py does first. What the DeviceListConfig/
# payloads add is the SINK's own knowledge of those peers: until a peer's ReportPhysicalAddress
# frame is injected, the plugin's device list holds no entry for it, whatever the emulator's map
# says. Every address in that list is fixed by Device_Config_Add_Network.yaml together with the
# vComponent's per-role address pools, and Init_Devicelist_Populate.verify_topology_consistency()
# is what keeps this comment and those documents from drifting apart.
send_key_press_event = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendKeyPressEvent","params":{"logicalAddress":5,"keyCode":65}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


send_user_control_pressed = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendUserControlPressed","params":{"logicalAddress":5,"keyCode":65}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


send_user_control_released = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.sendUserControlReleased","params":{"logicalAddress":5}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_active_path = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setActivePath","params":{"activePath":"1.0.0.0"}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_enabled_true = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setEnabled","params":{"enabled":true}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_enabled_false = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setEnabled","params":{"enabled":false}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_menu_language = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setMenuLanguage","params":{"language":"eng"}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


# THE WRITTEN VALUE IS EXPORTED, AND THE COMMAND IS BUILT FROM IT.
#
# A test case that writes this OSD name and then reads it back has to know what it wrote in
# order to assert the readback, and the only correct source for that is the command that did the
# writing. Restating the literal in the test case looks equivalent and is not: the two copies
# drift, and the drift shows up as a test that passes against the wrong value or fails against
# the right one. TCID10_Set_OSD_Name imports the constant below and requires exact equality
# against it, so changing the name here changes what that case demands, in one edit.
#
# The value is compared verbatim rather than normalised because the plugin returns it verbatim:
# OSDName::toString() in hdmicec/ccec/include/ccec/Operands.hpp returns the stored string
# unchanged, and this name is 6 characters against an OSDName MAX_LEN of 14, so nothing is
# truncated on the way through.
SET_OSD_NAME_VALUE = "Sky TV"

set_osd_name = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d",
    '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setOSDName","params":'
    f'{{"name":"{SET_OSD_NAME_VALUE}"}}}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


# THE THREE ROUTING-CHANGE REQUESTS, AND WHY THERE ARE THREE.
#
# setRoutingChange resolves each port name independently
# (HdmiCecSinkImplementation.cpp:2389-2427): a name containing "TV" is the television's own
# address, and anything else is parsed as "HDMI" followed by an input index that must exist in the
# port map. The two branches do different things to the sink's notion of the active source, and
# only the port names decide which:
#   - oldPort naming TV      -> m_currentActiveSource becomes -1 (nothing is the source)
#   - newPort naming TV      -> m_currentActiveSource becomes the television's own address
#   - neither naming TV      -> the addresses are resolved, <Routing Change> is broadcast, and
#                               m_currentActiveSource is NOT touched
# TCID19_Active_Path_Routing_Change_Flow needs all three, because a case that only ever sends the
# third shape cannot tell a working setRoutingChange from one that does nothing at all.
#
# The port names are named constants rather than three sets of literals so the pair that has to
# stay consistent - the input this suite treats as "some HDMI input" and the token the plugin
# matches for the television - is declared once. HDMI0 and HDMI1 are the two lowest input indices
# and so exist on any television with two or more HDMI inputs; a port index the device does not
# have is refused by the plugin before it broadcasts (cpp:2400/2424), which would make the request
# a silent no-op.
_ROUTING_TV_PORT = "TV"
_ROUTING_HDMI_PORT_A = "HDMI0"
_ROUTING_HDMI_PORT_B = "HDMI1"


def _set_routing_change_request(old_port, new_port):
    '''Build the curl argv for one setRoutingChange request.

    Three requests differ only in their two port names, so the argv is built once here rather
    than copied three times - a copy being where the timeout, the header or the endpoint drifts
    apart between siblings.
    Args:
        old_port: Value for the oldPort parameter, either "TV" or "HDMI<n>"
        new_port: Value for the newPort parameter, either "TV" or "HDMI<n>"
    Returns:
        A curl argv list in the same shape as every other constant in this module.
    '''
    return [
        "curl",
        "--max-time", "5",
        "--header", "Content-Type: application/json",
        "--request", "POST",
        "-d",
        '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setRoutingChange","params":'
        f'{{"oldPort":"{old_port}","newPort":"{new_port}"}}}}',
        "--",
        WPEFRAMEWORK_JSONRPC_URL,
    ]


# Input to input: resolves both addresses and broadcasts <Routing Change> without moving the
# active source. This is the pre-existing constant and its parameters are unchanged.
set_routing_change = _set_routing_change_request(
    _ROUTING_HDMI_PORT_A, _ROUTING_HDMI_PORT_B
)

# Input to television: makes the television the active source.
set_routing_change_to_tv = _set_routing_change_request(
    _ROUTING_HDMI_PORT_A, _ROUTING_TV_PORT
)

# Television to input: leaves nothing holding the active source.
set_routing_change_from_tv = _set_routing_change_request(
    _ROUTING_TV_PORT, _ROUTING_HDMI_PORT_B
)


setup_arc_routing_true = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setupARCRouting","params":{"enabled":true}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


setup_arc_routing_false = [
    "curl",
    "--max-time", "8",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setupARCRouting","params":{"enabled":false}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


# THE WRITTEN VALUE IS EXPORTED, AND THE COMMAND IS BUILT FROM IT - same contract as
# SET_OSD_NAME_VALUE above, and for the same reason: TCID12_Verify_Vendor_ID_Readback imports this
# constant and requires the readback to denote it, and TCID28_Invalid_VendorID_Nochange dispatches
# the set_vendor_id command below to re-establish it as its own baseline. The value therefore lives
# in exactly one place. (TCID28's second, DISTINGUISHING write - 0x00AABB - is its own constant and
# is deliberately not this one: it has to differ from both this value and the plugin's fallback,
# which are the same 0x0019FB.)
#
# Unlike the OSD name, this one CANNOT be compared verbatim, and the reason is in the
# middleware. getVendorId returns appVendorId.toString(), and CECBytes::toString() in
# hdmicec/ccec/include/ccec/Operands.hpp formats each byte with std::hex and NO zero padding
# and no "0x" prefix - so the three bytes 0x00, 0x19, 0xFB render as "019fb", not "0x0019FB".
# The two strings denote the same 24-bit identifier and differ only in presentation, so the
# comparison is made on the integer value: int("019fb", 16) == int("0x0019FB", 16) == 0x0019FB.
SET_VENDOR_ID_VALUE = "0x0019FB"

set_vendor_id = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d",
    '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setVendorId","params":'
    f'{{"vendorid":"{SET_VENDOR_ID_VALUE}"}}}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_latency_info = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setLatencyInfo","params":{"videoLatency":"2","lowLatencyMode":"1","audioOutputCompensated":"1","audioOutputDelay":"20"}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_vendor_id_invalid = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setVendorId","params":{"vllendorid":"0x0019FB"}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


set_osd_name_invalid = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setOSDName","params":{"nnamme":"Sky TV"}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]


setup_arc_routing_invalid = [
    "curl",
    "--max-time", "5",
    "--header", "Content-Type: application/json",
    "--request", "POST",
    "-d", '{"jsonrpc":"2.0","id":42,"method":"org.rdk.HdmiCecSink.setupARCRouting","params":{"ennabled":true}}',
    "--",
    WPEFRAMEWORK_JSONRPC_URL,
]
