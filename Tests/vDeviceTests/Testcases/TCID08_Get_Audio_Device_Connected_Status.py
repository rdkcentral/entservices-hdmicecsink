"""
/**
 * @file TCID08_Get_Audio_Device_Connected_Status.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID08_Get_Audio_Device_Connected_Status
 * @details Reads whether an HDMI-CEC audio device is currently connected to the sink by
 *          dispatching org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus over JSON-RPC, and
 *          validates the two fields the API publishes: result.connected and result.success.
 *          The connected flag is asserted TRUE, not merely asserted to be a boolean. It mirrors
 *          HdmiCecSinkImplementation::hdmiCecAudioDeviceConnected, which addDevice() sets true the
 *          moment a peer becomes present at CEC logical address 5 and which nothing else in the
 *          suite's first eight positions can clear. Init_Devicelist_Populate mandates that peer
 *          and SuitManager aborts when initialization fails, so the value is determined here
 *          rather than environment-dependent. The presence of address 5 in getDeviceList is
 *          asserted alongside it, so a False verdict says which of the two conditions broke.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with
 *    the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA
 *    AudioSystem peer at CEC logical address 5, and has left HDMI-CEC enabled.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus answers with a JSON-RPC result object
 *    carrying success true and a boolean connected field.
 *
 * @pass_criteria
 *  - result.success is True, result.connected is True, getDeviceList lists logical address 5,
 *    and run_test() returns True.
 *
 * @failure_criteria
 *  - An empty or sentinel response, a body that is not a JSON object, success not True,
 *    connected missing or not True, logical address 5 absent from getDeviceList, a JSON parsing
 *    error, or run_test() returns False.
 */
"""

import time
import json

from utils import (
    send_curl_command,
    sanitise_for_log,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
)
import HdmiCECSink_Curl as HdmiCecSinkApis


# The CEC logical address of an audio system, and the address Init_Devicelist_Populate bootstraps
# as a precondition of the whole suite. addDevice() keys the connected flag off exactly this value
# (HdmiCecSinkImplementation.cpp:2456-2459).
AUDIO_SYSTEM_LOGICAL_ADDRESS = 5


def _audio_system_present():
    '''Report whether getDeviceList currently lists the audio system at logical address 5.

    This is the precondition behind the connected assertion, read through a published method so
    the case can say WHY connected was false rather than only that it was. Every unreadable or
    off-contract reply answers False - the peer cannot be shown to be present - and each is
    logged, so an unreachable device is never mistaken for a discovered audio system.
    Returns:
        True only when the reply is a JSON object whose result reports success true and whose
        deviceList contains an entry for logical address 5.
    '''
    response = send_curl_command(HdmiCecSinkApis.get_device_list)
    if not response or response.startswith("< No response"):
        log_warning("  getDeviceList did not answer, so address 5 cannot be confirmed present")
        return False
    try:
        decoded = json.loads(response)
    except json.JSONDecodeError:
        log_warning("  getDeviceList reply is not valid JSON, so address 5 cannot be confirmed")
        return False
    result = decoded.get("result") if isinstance(decoded, dict) else None
    if not isinstance(result, dict) or result.get("success") is not True:
        log_warning("  getDeviceList did not report success, so address 5 cannot be confirmed")
        return False
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return False
    return any(
        isinstance(device, dict)
        and device.get("logicalAddress") == AUDIO_SYSTEM_LOGICAL_ADDRESS
        for device in device_list
    )


def run_test():
    start_time = time.perf_counter()

    log_info("Executing the curl command get audio device connected status")

    # The command is taken as a constant, never assembled here: HdmiCECSink_Curl.py owns the
    # method name, payload and timeout for this API, and a locally built request would be a
    # second definition free to drift from it.
    curl_response = send_curl_command(
        HdmiCecSinkApis.get_audio_device_connected_status
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # The transport failure guard that actually fires in this suite. utils.send_curl_command
    # returns the "< No response from WPEFramework >" sentinel - a TRUTHY string - for every
    # failure mode, so the falsy check above cannot catch one on its own. The prefix form is
    # the detection contract utils.py documents for callers.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        parsed = json.loads(curl_response)
        # A body that parses as JSON but is not an object, a JSON-RPC error envelope carrying
        # "error" instead of "result", and a malformed body carrying a non-object "result" all
        # collapse to an empty mapping, so the checks below report a missing field instead of
        # raising an AttributeError out of run_test(). The real payload stays intact for the
        # failure dump.
        envelope = parsed if isinstance(parsed, dict) else {}
        result = envelope.get("result", {})
        if not isinstance(result, dict):
            result = {}
        connected = result.get("connected")

        if result.get("success") is not True:
            log_error(
                "✖ getAudioDeviceConnectedStatus reported success="
                f"{sanitise_for_log(result.get('success'), max_chars=32)}, not True; the "
                "implementation sets that member unconditionally "
                "(HdmiCecSinkImplementation.cpp:1331-1336), so anything else means the reply is "
                "not the published shape"
            )
            log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
            log_error("TCID08_Get_Audio_Device_Connected_Status Failed ❌")
            return False

        if not isinstance(connected, bool):
            log_error(
                "✖ getAudioDeviceConnectedStatus reported a non-boolean connected member "
                f"({sanitise_for_log(connected, max_chars=64)})"
            )
            log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
            log_error("TCID08_Get_Audio_Device_Connected_Status Failed ❌")
            return False

        log_info(f"Observed audio device connected state: {connected}")

        # THE VALUE IS ASSERTED, AND THE PRECONDITION BEHIND IT IS ASSERTED FIRST.
        #
        # An earlier revision accepted EITHER boolean and left _audio_system_present() defined but
        # never called - so the case passed with no audio system connected at all, which is the
        # one outcome it exists to detect. It could not honestly have done more at the time: the
        # emulated network declared its audio-system peer as a Tuner, so logical address 5 was
        # never allocated and `connected` could only ever have been false.
        #
        # That is fixed. vcomponent_configurations/commands/Device_Config_Add_Network.yaml now
        # declares YAMAHA as an AudioSystem, whose vComponent address pool is the single value 5,
        # and Init_Devicelist_Populate.py bootstraps that address specifically and FAILS if the
        # middleware never registers it. So by the time this case runs, address 5 is present by
        # construction - and `hdmiCecAudioDeviceConnected` is set inside addDevice() for exactly
        # that address (HdmiCecSinkImplementation.cpp:2456-2459-2459) and cleared only by
        # removeDevice() for it (:2503), neither of which any earlier case in the suite calls.
        #
        # The two readings are taken in this order deliberately. When the flag is false, the
        # device list says whether the cause is a peer that is absent - a topology or seeding
        # failure, upstream of this API - or a peer that is present while the flag disagrees with
        # it, which is a defect in the plugin's own bookkeeping. The diagnostics name which.
        #
        # (The L2 suite's GetAudioDeviceConnectedStatus_JSONRPC case asserts EXPECT_FALSE for the
        # same member, and that is not a contradiction: its in-process host discovers no peers at
        # all, so false is correct there for the same reason true is correct here.)
        present = _audio_system_present()
        if not present:
            log_error(
                f"✖ getDeviceList does not list logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS}, "
                "so the audio-system precondition this case rests on was never established. "
                "Init_Devicelist_Populate.py bootstraps that address and fails if the middleware "
                "does not register it, so reaching this point means the device list lost a peer "
                "it had already learned."
            )
            log_error("TCID08_Get_Audio_Device_Connected_Status Failed ❌")
            return False
        log_success(
            f"✔ logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} is present in the device list"
        )

        if connected is not True:
            log_error(
                f"✖ the audio system is discovered at logical address "
                f"{AUDIO_SYSTEM_LOGICAL_ADDRESS} but getAudioDeviceConnectedStatus reports "
                "connected=False. addDevice() sets hdmiCecAudioDeviceConnected for that address "
                "(HdmiCecSinkImplementation.cpp:2456-2459-2459) and only removeDevice() for it clears "
                "the flag (:2503), so the device list and the flag disagreeing is a defect in "
                "the plugin's bookkeeping rather than a missing precondition."
            )
            log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
            log_error("TCID08_Get_Audio_Device_Connected_Status Failed ❌")
            return False

        log_success("✔ connected reports True, consistent with the discovered audio system")
        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID08_Get_Audio_Device_Connected_Status Passed ✅", elapsed_time))
        return True
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID08_Get_Audio_Device_Connected_Status Failed ❌")
        return False
