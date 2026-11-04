"""
/**
 * @file TCID11_Set_Vendor_ID.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *        Writes the sink's advertised vendor identifier over JSON-RPC and asserts the
 *        success acknowledgement.
 *
 * @testcase TCID11_Set_Vendor_ID
 * @details Dispatches org.rdk.HdmiCecSink.setVendorId with the vendor identifier published by
 *          HdmiCECSink_Curl.set_vendor_id and asserts that the device answers with the whole
 *          expected JSON-RPC envelope, success member included. The request - method,
 *          parameters and the vendor identifier itself - is owned entirely by that sibling
 *          constant; this module never composes a payload of its own, so the value written
 *          here cannot drift from the value the readback case expects.
 *
 *          PRODUCER OF AN ORDERED PAIR - the one thing to understand before editing this
 *          module. SuitManager.py registers this case at position 11 and
 *          TCID12_Verify_Vendor_ID_Readback at position 12, and that order is load-bearing
 *          rather than cosmetic: this case ESTABLISHES the vendor identifier that TCID12 READS
 *          BACK through getVendorId. Two consequences follow, and both are deliberate. This
 *          module performs no readback of its own, because verification is TCID12's
 *          responsibility and duplicating it here would blur the pair's division of labour.
 *          And this module DELIBERATELY DOES NOT RESTORE the previous vendor identifier: a
 *          restore would overwrite the very value the next case exists to observe, turning a
 *          green pair red.
 *
 *          The residual state that leaves behind is safe by suite design rather than by luck.
 *          TCID04_Get_Vendor_ID runs earlier, at position 4, so the device's original identifier
 *          is observed before this case writes over it; and no case that follows depends on the
 *          pre-existing identifier. TCID28_Invalid_VendorID_Nochange, at position 28, writes a
 *          DIFFERENT distinguishing identifier of its own and then restores through its cleanup()
 *          hook whatever identifier it found on entry - which is this case's value when the suite
 *          runs in order - so the value written here survives the rest of the suite.
 *
 *          Boundary and malformed-input sweeping of setVendorId is not attempted here. It is
 *          already covered at L1 - setVendorId_Boundary, setVendorId_MinValue,
 *          setVendorId_ValidHex, setVendorId_InvalidFormat, setVendorIdParamMissing and
 *          MalformedJSON_setVendorId - and the sink command module publishes no boundary
 *          constant. What is missing, and what this case supplies, is the device-level leg.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint: a device under test -
 *    physical hardware or a QEMU target - hosts org.rdk.HdmiCecSink and answers at
 *    utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate.run_test() has already seeded the CEC topology and left HDMI-CEC
 *    enabled; SuitManager.py runs it once, before the first test case.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository. No continuous integration
 *    workflow runs it, none of the prerequisites above is present in a build environment, and
 *    nothing described here has been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - setVendorId is accepted, and the sink advertises the vendor identifier written here until
 *    TCID12_Verify_Vendor_ID_Readback has read it back.
 *
 * @pass_criteria
 *  - The reply equals {"jsonrpc":"2.0","id":42,"result":{"success":true}} and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - An empty or sentinel response, a payload differing from the expected envelope in any
 *    member, a JSON parse error, or run_test() returning False.
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


# The vendor identifier standing on the device before this case wrote to it.
#
# Published here rather than restored here on purpose. This case is the WRITE half of an ordered
# pair, and the value it writes IS the fixture TCID12_Verify_Vendor_ID_Readback runs against at the
# next registration position - so a restore performed here would delete that fixture before its
# only consumer saw it. TCID12 owns the restore instead, and reads this slot to know what to put
# back; SuitManager.py's TEST_DEPENDENCIES map already declares that pairing, so the coupling is
# documented rather than implicit. None means the baseline could not be read, in which case TCID12
# leaves the setting alone rather than writing a guess.
CAPTURED_VENDOR_ID = None


def run_test():
    start_time = time.perf_counter()

    # The WHOLE envelope is compared, not just the success member, so a reply carrying the right
    # success flag under a wrong id or a wrong protocol version is still a failure. The id is 42
    # because every request constant in HdmiCECSink_Curl.py sends "id":42.
    expected_output_response = {
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "success": True
        }
    }

    # Baseline capture, before anything is written, and published for TCID12 to restore. This is
    # the only place the pre-write identifier is observable: by the time the reader runs, this case
    # has already overwritten it.
    global CAPTURED_VENDOR_ID
    baseline = send_curl_command(HdmiCecSinkApis.get_vendor_id)
    if baseline and not baseline.startswith("< No response"):
        try:
            baseline_envelope = json.loads(baseline)
        except json.JSONDecodeError:
            baseline_envelope = None
        baseline_result = (
            baseline_envelope.get("result") if isinstance(baseline_envelope, dict) else None
        )
        captured = baseline_result.get("vendorid") if isinstance(baseline_result, dict) else None
        if isinstance(captured, str) and captured.strip():
            CAPTURED_VENDOR_ID = captured
            log_info(
                "Captured the pre-write vendor identifier for "
                f"TCID12 to restore: {sanitise_for_log(captured, max_chars=64)}"
            )
    if CAPTURED_VENDOR_ID is None:
        # Not fatal, and not silent. The write and its envelope assertion below are this case's
        # subject and they do not depend on the baseline; what is lost is only the pair's ability
        # to leave the setting as it found it, which TCID12 reports rather than guesses at.
        log_warning(
            "The pre-write vendor identifier could not be read, so the TCID11/TCID12 pair will "
            "leave the written value in place and TCID12 will say so"
        )

    log_info("Executing the curl command set vendor id")

    # The sibling constant is dispatched verbatim. The vendor identifier lives there and only
    # there - TCID12_Verify_Vendor_ID_Readback imports HdmiCECSink_Curl.SET_VENDOR_ID_VALUE to
    # form its expectation, and TCID28_Invalid_VendorID_Nochange dispatches this same command to
    # re-establish the value as its baseline - so no hex literal and no hand-built payload appears
    # in this module, and an edit to one side of the pair cannot silently desynchronise the other.
    curl_response = send_curl_command(
        HdmiCecSinkApis.set_vendor_id
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command reports every transport failure as the byte-exact
    # "< No response from WPEFramework >" sentinel. That is a TRUTHY string, so it survives the
    # emptiness check above and needs its own guard - the prefix test utils.py documents. Without
    # it an unreachable device would be carried into json.loads and misreported as a payload
    # mismatch, which points at the plugin instead of at the missing endpoint.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        if json.loads(curl_response) == expected_output_response:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID11_Set_Vendor_ID Passed ✅", elapsed_time))
            return True
        else:
            log_error("TCID11_Set_Vendor_ID Failed ❌")
            return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID11_Set_Vendor_ID Failed ❌")
        return False
    # NO `finally:` RESTORE CLAUSE HERE, AND ITS ABSENCE IS THE DELIBERATE CHOICE.
    #
    # This is where the suite's other write cases put their restore - TCID08_Set_Enabled_False in
    # the source suite resets its flag from exactly this position - and this case must not. The
    # vendor identifier written above IS the fixture that TCID12_Verify_Vendor_ID_Readback runs
    # against at the next registration position; restoring it here would delete that fixture
    # before its only consumer ever saw it, and TCID12 would fail for a reason with nothing to do
    # with the plugin under test. The dependency between the two cases is therefore documented
    # rather than accidental, and SuitManager.py's registration list is the mechanism that
    # guarantees the ordering it needs.
    #
    # The PAIR is state-neutral even so: this case publishes CAPTURED_VENDOR_ID above and TCID12
    # restores it from its own cleanup() hook, after it has asserted the written value. So the
    # restore happens once, at the point where the fixture has finished being useful, rather than
    # not at all - which is what an earlier revision left, with both halves declining to own it.
