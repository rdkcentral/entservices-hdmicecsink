"""
/**
 * @file TCID02_Get_Devicelist.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID02_Get_Devicelist
 * @details Validates the 'TCID02_Get_Devicelist' HDMI CEC Sink behavior through the
 *          org.rdk.HdmiCecSink.getDeviceList JSON-RPC method. The response envelope is
 *          decoded once and evaluated through NAMED boolean predicates - one per field the
 *          interface publishes ('numberofdevices', 'deviceList', 'success') - so the check
 *          that broke is identifiable from the logged payload rather than flattened into a
 *          single opaque comparison.
 *
 *          The case is READ-ONLY: it observes the device list the suite's initialization
 *          module already established, alters no device state, and therefore carries no
 *          restore step. It AUTHORS a device-level request and evaluates the answer; it
 *          never starts, emulates or stubs the services that answer it, and a request that
 *          does not reach a live target is reported as a failure rather than tolerated.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over JSON-RPC at the endpoint
 *    utils.py resolves into WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has seeded the emulated CEC topology, so the audio-system
 *    bootstrap peer at logical address 5 is present in the sink's device list.
 *  - Target environment is ready for HDMI CEC emulation/command execution.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - getDeviceList answers with success true, an integer device count of at least one, and
 *    a deviceList array whose entries are consistent with that count.
 *
 * @pass_criteria
 *  - 'success' is True, 'numberofdevices' is an int that is NOT a bool, at least one device is
 *    reported, the 'deviceList' array is consistent with the count, every entry is a dict carrying
 *    a 'logicalAddress' that is an int and not a bool, and run_test() returns True.
 *
 * @failure_criteria
 *  - Response mismatch, command failure, JSON parsing error, or testcase returns False. A boolean
 *    supplied where a device count or a logical address is required is a mismatch, not a number:
 *    bool is a subclass of int in Python, so both numeric fields are checked with
 *    utils.is_plain_int rather than a bare isinstance.
 */
"""


import time
import json
from utils import (
    send_curl_command,
    is_plain_int,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def run_test():
    start_time = time.perf_counter()

    log_info("Executing the curl command get device list")

    curl_response = send_curl_command(HdmiCecSinkApis.get_device_list)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # send_curl_command reports a transport failure by RETURNING the TRUTHY sentinel string
    # "< No response from WPEFramework >", which the guard above cannot see and which
    # json.loads would misreport as a payload mismatch rather than as the unreachable device
    # it actually is. Testing the prefix is the suite's own idiom for detecting it.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        actual_output_response = json.loads(curl_response)

        # A payload that parses as JSON but is not an object, or whose "result" member is not
        # an object, is a response MISMATCH that must fail through the predicates below rather
        # than escape from here as an AttributeError - run_test() owes its caller a bool on
        # every path. The empty mapping substituted here leaves the real payload intact for
        # the failure dump, so nothing is hidden by the substitution.
        envelope = actual_output_response if isinstance(actual_output_response, dict) else {}
        result = envelope.get("result", {})
        if not isinstance(result, dict):
            result = {}

        has_success = result.get("success") is True
        # utils.is_plain_int, not isinstance(..., int): bool is a SUBCLASS of int in Python, so a
        # bare isinstance check would accept {"numberofdevices": true} as a valid device count -
        # and, further down, True >= 1 would then satisfy the "at least one device" requirement
        # as well. Every numeric field in this case is validated through that one predicate.
        has_count = is_plain_int(result.get("numberofdevices"))

        count = result.get("numberofdevices")
        device_list = result.get("deviceList")
        if count == 0:
            list_consistent = (device_list is None) or (
                isinstance(device_list, list) and len(device_list) == 0
            )
        else:
            # Some targets report count excluding placeholder/NA devices, so
            # the list length can be greater than numberofdevices.
            list_consistent = isinstance(device_list, list) and len(device_list) >= count

        entries_valid = True
        if isinstance(device_list, list):
            for dev in device_list:
                if not isinstance(dev, dict):
                    entries_valid = False
                    break
                # A logical address is an integer in the published contract; a boolean in that
                # field is an off-contract reply, and isinstance(False, int) would have let it
                # through as address 0 - the TV's own address, which is the one value that would
                # look plausible in a diagnostic.
                if not is_plain_int(dev.get("logicalAddress")):
                    entries_valid = False
                    break

        # Required rather than merely tolerated: Init_Devicelist_Populate.run_test() posts
        # Device_Config_Add_Network.yaml and polls until the audio-system bootstrap peer at
        # logical address 5 appears, aborting the suite when it never does - so an empty
        # device list reaching this case is a regression, not a valid topology.
        has_devices = is_plain_int(count) and count >= 1

        if has_success and has_count and has_devices and list_consistent and entries_valid:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID02_Get_Devicelist Passed ✅", elapsed_time))
            return True

        log_warning(
            f"Actual  : {json.dumps(actual_output_response, indent=2, sort_keys=True)}"
        )
        log_error("TCID02_Get_Devicelist Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID02_Get_Devicelist Failed ❌")
        return False
