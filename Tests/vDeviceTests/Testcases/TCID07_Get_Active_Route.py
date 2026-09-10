"""
/**
 * @file TCID07_Get_Active_Route.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID07_Get_Active_Route
 * @details Reads the sink's active route over JSON-RPC (org.rdk.HdmiCecSink.getActiveRoute)
 *          and validates the availability flag, the path list and the route string together
 *          with their mutual consistency. This is the device-level leg of the sink's route
 *          resolution path: HdmiCecSinkImplementation::getActiveRoute
 *          (HdmiCecSinkImplementation.cpp:1958) and the nested port-map walk it delegates to,
 *          HdmiPortMap::getRoute (HdmiCecSinkImplementation.h:351), were both catalogued as
 *          zero-hit, and GetActiveRoute as covered by the sink's own L2 suite with no
 *          end-to-end leg, because before this change the sink had no device-level suite at
 *          all (COVERAGE_GAPS.md, "Missing sink device-level (E2E) suite", P1). Every one of
 *          those statements is the gap register's PRE-CHANGE BASELINE, not a description of
 *          the tree this file sits in: the suite that closes the "no device-level suite" gap
 *          is the one this module belongs to. It supplies the missing leg, and claims no
 *          coverage change: the suite is authored here and not executed, so such a claim
 *          would be unmeasured.
 *
 *          The route text is read from the key "ActiveRoute", with a capital A - the one
 *          field of the sink's JSON-RPC surface that is not lowerCamelCase
 *          (IHdmiCecSink.h:191), so it is spelled deliberately and not by habit.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - hosts the org.rdk.HdmiCecSink
 *    plugin and answers JSON-RPC at utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has run, so the emulated CEC network is configured, HDMI-CEC is
 *    enabled and the device list is seeded; a multi-hop route resolves only once a peer
 *    beneath the television has become the active source.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository: no continuous integration
 *    workflow runs it, and nothing below has been observed against a device or an emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - getActiveRoute answers with success true, an "available" boolean, and - when a route is
 *    available - a route description consistent with the reported route length.
 *
 * @pass_criteria
 *  - result.success is True, result.available is a bool, and when available is True the
 *    length, pathList and ActiveRoute fields are well formed and mutually consistent;
 *    run_test() returns True.
 *
 * @failure_criteria
 *  - The command cannot be sent, the transport sentinel comes back, the body is not JSON,
 *    success is not True, available is not a bool, an available route is malformed or
 *    self-inconsistent, or run_test() returns False.
 */
"""


import time
import json
from utils import (
    send_curl_command,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def run_test():
    start_time = time.perf_counter()

    log_info("Executing the curl command get active route")

    curl_response = send_curl_command(HdmiCecSinkApis.get_active_route)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command reports every transport failure as this byte-exact sentinel,
    # which is TRUTHY and therefore survives the emptiness check above. Without this second
    # guard an unreachable device would reach json.loads and be misreported as a parse error.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        actual_output_response = json.loads(curl_response)

        # An error reply carries no "result", and send_curl_command returns the first line that
        # parses as JSON at all - which need not be an object. Both are normalised to an empty
        # mapping so the predicates stay plain .get() calls and this function keeps its
        # contract of returning a bool on every path rather than raising into the suite runner.
        envelope = actual_output_response if isinstance(actual_output_response, dict) else {}
        result = envelope.get("result")
        if not isinstance(result, dict):
            result = {}

        has_success = result.get("success") is True
        has_available = isinstance(result.get("available"), bool)

        available = result.get("available")
        length = result.get("length")
        path_list = result.get("pathList")
        active_route = result.get("ActiveRoute")

        if available is True:
            # A route is being reported, so its description must be well formed. The route
            # string is the only field the plugin sets on BOTH available-true branches, so it
            # is the one REQUIRED field, and it must be non-empty: an available route with no
            # description is not a route, which is the same verdict the sink's own L2 test
            # reaches. length and pathList are checked only WHEN PRESENT, because the
            # television being its own active source yields available true with ActiveRoute
            # "TV" and neither a length nor a path list
            # (HdmiCecSinkImplementation.cpp:1527-1531) - the L2 test guards its iterator the
            # same way, with `if (pathList != nullptr)`.
            route_valid = isinstance(active_route, str) and active_route != ""

            # bool is a subclass of int, so a response rendering length as true/false would
            # otherwise pass an isinstance(int) test.
            if length is not None and (
                not isinstance(length, int) or isinstance(length, bool)
            ):
                route_valid = False

            if path_list is not None and not isinstance(path_list, list):
                route_valid = False

            if isinstance(path_list, list):
                # The contract publishes a hop as an object (logicalAddress, physicalAddress,
                # deviceType, vendorID, osdName) but documents the field only as "List of
                # active path", so a hop rendered as a plain string is accepted too:
                # over-constraining an under-specified shape reports a defect that is not one.
                for hop in path_list:
                    if not isinstance(hop, (dict, str)):
                        route_valid = False
                        break

                # Cross-check, in the only direction the implementation permits. "length" is
                # the length of the ROUTE (IHdmiCecSink.h:187), taken from route.size(), while
                # the path list is built by skipping every UNREGISTERED hop of that route
                # (HdmiCecSinkImplementation.cpp:1489-1501). len(pathList) is therefore at most
                # length, and demanding equality would fail a correct device. A path list
                # LONGER than the declared route length is still a real defect, and is caught.
                if isinstance(length, int) and not isinstance(length, bool):
                    if len(path_list) > length:
                        route_valid = False
        else:
            # available is False, or absent - has_available already fails on absent. The
            # plugin answers {"available":false,"length":0,"ActiveRoute":"","success":true}
            # when no peer is the active source, so an empty route set is the correct reply
            # and demanding a populated route here would be a false failure.
            route_valid = True

        log_info(
            f"available: {available}  length: {length}  "
            f"pathList entries: {len(path_list) if isinstance(path_list, list) else 'absent'}"
            f"  ActiveRoute: {active_route!r}"
        )

        if has_success and has_available and route_valid:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID07_Get_Active_Route Passed ✅", elapsed_time))
            return True

        log_warning(
            f"Actual  : {json.dumps(actual_output_response, indent=2, sort_keys=True)}"
        )
        log_error("TCID07_Get_Active_Route Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID07_Get_Active_Route Failed ❌")
        return False
