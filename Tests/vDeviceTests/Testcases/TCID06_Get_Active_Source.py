"""
/**
 * @file TCID06_Get_Active_Source.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID06_Get_Active_Source
 * @details Reads the current active source from the sink over JSON-RPC and validates the
 *          availability flag plus, when a source is available, the peer detail fields that
 *          describe it. The sink answers org.rdk.HdmiCecSink.getActiveSource with a ten
 *          member result block - available, logicalAddress, physicalAddress, deviceType,
 *          cecVersion, osdName, vendorID, powerStatus, port and success - and this case
 *          asserts the SHAPE of that block rather than the identity of the source, because
 *          which peer holds the active source depends on which one last announced itself and
 *          no case ahead of this one in the suite's declared order forces a particular peer.
 *
 *          The case is a READ-ONLY probe: it issues one query, restores nothing, and leaves
 *          the device exactly as it found it. That is why it sits inside the suite's opening
 *          read-only block, ahead of every case that writes to the device, and it is what
 *          lets the later active-source flow cases reuse the same API as their own
 *          before/after probe without inheriting any state from here.
 *
 *          Only what a JSON-RPC query can observe is asserted. The sink also publishes an
 *          active-source notification, but a curl-driven device-level case cannot subscribe
 *          to it, so nothing here is written as an event assertion.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable via the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has seeded the emulated topology, so the sink knows peers whose
 *    details can be reported when one of them holds the active source.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The query succeeds and reports availability; when a source is available its detail
 *    fields accompany the flag with the documented types.
 *
 * @pass_criteria
 *  - result.success is True, result.available is a bool, and when available is True the
 *    detail fields are present with the right types; run_test() returns True.
 *
 * @failure_criteria
 *  - Response mismatch, command failure, JSON parsing error, or testcase returns False.
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

    log_info("Executing the curl command get active source")

    # HdmiCecSinkApis.get_active_source is an argv LIST constant, not a callable: it is passed
    # to send_curl_command as inert data and executed there without a shell.
    curl_response = send_curl_command(HdmiCecSinkApis.get_active_source)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # Two guards rather than one, because they catch different failures. The sentinel that
    # send_curl_command returns on any transport failure - "< No response from WPEFramework >"
    # - is a NON-EMPTY string, so the falsy check above cannot see it. Without this second
    # guard an unreachable device would fall through to json.loads and be misreported as a
    # malformed payload instead of as the transport failure it actually is. The prefix tested
    # here is the one utils.py documents callers to test.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        actual_output_response = json.loads(curl_response)

        # A payload that parses as JSON but is not an object, and a "result" member that is not
        # an object, are response MISMATCHES that must fail through the predicates below rather
        # than escape from here as an AttributeError - run_test() owes its caller a bool on
        # every path, and a scalar or a list reaches exactly the same .get() call as an object
        # does. The empty mapping substituted here leaves the real payload intact for the
        # failure dump, so the substitution hides nothing.
        envelope = actual_output_response if isinstance(actual_output_response, dict) else {}
        result = envelope.get("result", {})
        if not isinstance(result, dict):
            result = {}

        has_success = result.get("success") is True
        has_available = isinstance(result.get("available"), bool)

        available = result.get("available")

        # The detail predicate is CONDITIONAL, and that is the point rather than a shortcut.
        # A sink holding no current active source is in a legitimate steady state: it reports
        # availability alone and leaves the eight detail members unset, so they arrive blank
        # or are absent from the response altogether. Requiring populated details in that
        # state would fail a correctly behaving device, so the predicate is satisfied
        # trivially when no source is active and is only enforced when one is.
        if available is True:
            details_valid = isinstance(result.get("logicalAddress"), int) and all(
                isinstance(result.get(field), str)
                for field in (
                    "physicalAddress",
                    "deviceType",
                    "cecVersion",
                    "osdName",
                    "vendorID",
                    "powerStatus",
                    "port",
                )
            )
        else:
            details_valid = True

        # Logged before the verdict so the run record carries what was observed whether the
        # case passes or fails, and logged as an observation rather than an assertion: no
        # particular logical address is expected here.
        log_info(f"  Active source available: {available}")
        if available is True:
            log_info(
                f"  Active source logicalAddress: {result.get('logicalAddress')}"
                f"  osdName: {result.get('osdName')}"
            )

        if has_success and has_available and details_valid:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID06_Get_Active_Source Passed ✅", elapsed_time))
            return True

        log_warning(
            f"Actual  : {json.dumps(actual_output_response, indent=2, sort_keys=True)}"
        )
        log_error("TCID06_Get_Active_Source Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID06_Get_Active_Source Failed ❌")
        return False
