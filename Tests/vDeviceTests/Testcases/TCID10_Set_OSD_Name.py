"""
/**
 * @file TCID10_Set_OSD_Name.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID10_Set_OSD_Name
 * @details Sets the sink television's OSD name over JSON-RPC through
 *          org.rdk.HdmiCecSink.setOSDName and confirms the write actually landed by reading the
 *          value straight back with org.rdk.HdmiCecSink.getOSDName. The pre-existing name is
 *          captured and logged before anything is written, so the run record shows the
 *          transition rather than only the end state. A reply that merely reports success is
 *          not accepted as proof on its own; the read-back is what makes this an assertion, and
 *          the read-back is compared for EQUALITY against the value the request sent rather
 *          than merely for being a non-empty string - an OSD name is a persistent device
 *          setting, so a non-empty reading is also what a discarded write would leave behind.
 *
 *          RESIDUAL STATE IS DELIBERATE AND DOCUMENTED. This case leaves the OSD name at the
 *          deterministic value HdmiCECSink_Curl.SET_OSD_NAME_VALUE holds instead of
 *          writing the captured baseline back, because that module publishes exactly one
 *          set_osd_name constant carrying one fixed name and no inverse, and because
 *          hand-building a JSON-RPC payload here to synthesise a restore is refused. The
 *          reasoning, and why the residual is safe under the suite's pinned execution order,
 *          is recorded in full immediately above the write in run_test().
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is reachable and hosts an
 *    active org.rdk.HdmiCecSink plugin answering JSON-RPC at utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has seeded the emulated CEC topology, which SuitManager.py
 *    guarantees by running it once before the first test case.
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
 *  - setOSDName answers {"jsonrpc":"2.0","id":42,"result":{"success":true}} and the following
 *    getOSDName reports success together with an OSD name EQUAL to the value the request
 *    carried - HdmiCECSink_Curl.SET_OSD_NAME_VALUE, imported rather than restated here.
 *
 * @pass_criteria
 *  - The setOSDName reply equals the expected
 *    {"jsonrpc":"2.0","id":42,"result":{"success":true}} payload, the read-back reports success
 *    with name == HdmiCECSink_Curl.SET_OSD_NAME_VALUE exactly, and run_test() returns True.
 *
 * @failure_criteria
 *  - Response mismatch, command failure, an unreachable endpoint, a read-back carrying success
 *    false, an absent or empty name, or ANY name other than the one written - a stale name a
 *    previous run left behind is a failure, not a pass - JSON parsing error, or run_test()
 *    returns False.
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


# The write is applied asynchronously, so the read-back is polled rather than slept out. The
# names follow the convention every other bounded observer in this suite uses
# (<PURPOSE>_TIMEOUT_S / <PURPOSE>_POLL_S), so a reader who has met one has met them all.
# The budget is generous relative to a local apply and the interval is short, which is the
# combination that makes a fast apply fast and a slow one visible rather than fatal.
READBACK_TIMEOUT_S = 10.0
READBACK_POLL_S = 0.25


def _osd_result(curl_response):
    '''Return the JSON-RPC "result" member of a getOSDName reply, or None.

    getOSDName is dispatched twice by this case - once for the informational baseline and once
    for the assertive read-back - so the envelope handling lives here instead of being written
    out twice. Extraction only: the caller keeps the decision about what a missing result
    means, which is what lets the baseline treat it as informational while the read-back
    treats it as a failure. Every unusable reply collapses to None rather than raising - a
    falsy response, the transport-failure sentinel, a body that does not parse, a body that is
    not a JSON object, and an envelope with no "result" member all yield None.
    Args:
        curl_response: Raw response string exactly as utils.send_curl_command returned it.
    Returns:
        The "result" member as a dict when the reply carried a usable one, otherwise None.
    '''
    if not curl_response or curl_response.startswith("< No response"):
        return None

    try:
        envelope = json.loads(curl_response)
    except json.JSONDecodeError:
        return None

    if not isinstance(envelope, dict):
        return None

    result = envelope.get("result")
    return result if isinstance(result, dict) else None


def run_test():
    '''Set the sink's OSD name and confirm the write with a read-back.

    Returns:
        True only when setOSDName answered with the expected success envelope AND the
        subsequent getOSDName reported success with a name equal to
        HdmiCECSink_Curl.SET_OSD_NAME_VALUE, the value the request carried. False on a command
        that could not be sent, an unreachable endpoint, an unexpected reply, an unusable
        read-back, a name other than the one written, or a JSON parsing error.
    '''
    start_time = time.perf_counter()

    # The id is 42 because every constant in HdmiCECSink_Curl.py sends "id":42, and setOSDName
    # returns HdmiCecSinkSuccess, which serialises to a bare {"success": true} result.
    expected_output_response = {
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "success": True
        }
    }

    # Baseline capture, before anything is written, so the transition is visible in the run
    # record. A baseline that never arrived is NOT fatal and is logged rather than returned on:
    # the write and the read-back below are the actual assertion, and aborting because an
    # informational read failed would report a defect that is not there.
    baseline_get = send_curl_command(HdmiCecSinkApis.get_osd_name)
    log_warning(f"Baseline getOSDName response: {baseline_get}")

    baseline_result = _osd_result(baseline_get)
    baseline_name = baseline_result.get("name") if baseline_result else None
    if baseline_name is None:
        log_warning("Baseline OSD name unavailable - continuing, it is informational only")

    # RESIDUAL STATE, REPORTED RATHER THAN FORCED. The write below leaves the OSD name at the
    # deterministic value HdmiCECSink_Curl.set_osd_name encodes; this case does not put the
    # captured baseline back. That is a decision, not an omission:
    #
    #   * HdmiCECSink_Curl.py publishes exactly ONE set_osd_name constant carrying ONE fixed
    #     name, so no constant exists that could write an arbitrary captured name back. The
    #     suite's `finally:  #reset the state` idiom works for the enabled flag only because
    #     that API has an inverse constant - set_enabled_true beside set_enabled_false.
    #     setOSDName has no inverse.
    #   * Hand-building a JSON-RPC payload here to restore the captured name is refused.
    #     Payload construction belongs to HdmiCECSink_Curl.py, whose own contract forbids
    #     assembling or concatenating its commands elsewhere; forking that transport contract
    #     into a test case to synthesise a restore would be the larger defect.
    #
    # Leaving the residual is safe under the execution order pinned in SuitManager.py:
    #   (a) the only reader of the prior value, TCID03_Get_OSD_Name, runs EARLIER at position 3
    #       and has already observed and asserted the pre-write name by the time this case, at
    #       position 10, changes it; and
    #   (b) TCID29_Invalid_OSD_Setnochange re-establishes the same value through the same
    #       set_osd_name constant at position 29, so the suite ends on the value set here.
    #
    # A `finally` block re-issuing set_osd_name would LOOK like a restore while restoring
    # nothing. Reporting the residual is Directive 6's "report, don't force" applied to
    # fixture state.
    log_info("Executing the curl command set OSD name")

    curl_response = send_curl_command(
        HdmiCecSinkApis.set_osd_name
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command reports every transport failure with a TRUTHY sentinel string, so
    # the falsy check above cannot catch it and this second guard is load-bearing. Without it an
    # unreachable endpoint would fall through to the comparison and be reported as a response
    # mismatch, misdiagnosing a dead endpoint as a plugin defect.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework for set OSD name")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        if json.loads(curl_response) != expected_output_response:
            log_error("TCID10_Set_OSD_Name Failed ❌")
            return False

        # THE APPLY IS OBSERVED, NOT WAITED OUT.
        #
        # setOSDName is applied asynchronously, so the read-back needs a settling window, and
        # a fixed pause is the wrong shape for that window in both directions: on a host
        # slower than the guess this case fails for a write that was about to land, and on
        # every other host it spends the whole guess even when the value arrived in the first
        # millisecond. Neither behaviour is a property of the thing under test, which makes
        # the verdict depend on the host rather than on the plugin.
        #
        # This loop polls the observable itself - the name getOSDName reports - and it does
        # NOT hide a slow apply behind a retry, which was the stated objection to a poll here
        # and is worth answering directly: it exits the instant the value matches, measures
        # how long that took, and REPORTS that duration below, so an apply that needed most
        # of the budget appears in the output instead of being smoothed away. If the budget
        # expires, the last response observed is carried out of the loop and reported verbatim
        # by the three checks that follow, unchanged - which is a diagnosis a fixed pause
        # cannot give, because it separates "never applied" from "applied too late".
        poll_started = time.perf_counter()
        readback_deadline = time.monotonic() + READBACK_TIMEOUT_S
        readback_result = None
        while True:
            readback_result = _osd_result(send_curl_command(HdmiCecSinkApis.get_osd_name))
            if (
                readback_result is not None
                and readback_result.get("success") is True
                and readback_result.get("name") == HdmiCecSinkApis.SET_OSD_NAME_VALUE
            ):
                break
            if time.monotonic() >= readback_deadline:
                break
            time.sleep(READBACK_POLL_S)
        settle_seconds = time.perf_counter() - poll_started
        log_info(
            f"  OSD name read-back settled after {settle_seconds:.3f}s "
            f"(budget {READBACK_TIMEOUT_S:.1f}s)"
        )

        if readback_result is None:
            log_error("✖ read-back of the OSD name returned no usable response")
            log_error("TCID10_Set_OSD_Name Failed ❌")
            return False

        if readback_result.get("success") is not True:
            log_error(f"✖ read-back did not report success: {readback_result}")
            log_error("TCID10_Set_OSD_Name Failed ❌")
            return False

        # THE READ-BACK MUST EQUAL WHAT THIS CASE WROTE, EXACTLY.
        #
        # A non-empty-string check is not a verification of this case's write: the OSD name is
        # a persistent device setting, so whatever a previous run or a previous case left
        # behind is also a non-empty string, and so is a name the plugin never changed. The
        # check would pass with the write silently discarded, which is the one outcome this
        # case exists to detect.
        #
        # The literal is NOT repeated here. HdmiCECSink_Curl.SET_OSD_NAME_VALUE is the value the
        # request above sends, exported by the module that sends it, and imported here - so the
        # write and the expectation are two uses of one constant rather than two copies of one
        # string. That is what makes the comparison safe against a constant change: change the
        # name there and this case demands the new name, in one edit. Coupling the two modules
        # on the VALUE is the point; the alternative was decoupling them into disagreement.
        #
        # Compared verbatim rather than normalised, because the plugin returns it verbatim:
        # OSDName::toString() in hdmicec/ccec/include/ccec/Operands.hpp returns the stored
        # string unchanged, and this name is 6 characters against an OSDName MAX_LEN of 14, so
        # nothing is truncated on the way through.
        final_name = readback_result.get("name")
        if final_name != HdmiCecSinkApis.SET_OSD_NAME_VALUE:
            log_error(
                f"✖ read-back reports OSD name {final_name!r}, expected "
                f"{HdmiCecSinkApis.SET_OSD_NAME_VALUE!r} - the value setOSDName was asked to "
                "write. An absent or empty value means the write was not applied; a different "
                "string means the device kept an earlier name or truncated this one"
            )
            log_warning(f"Actual  : {json.dumps(readback_result, indent=2, sort_keys=True)}")
            log_error("TCID10_Set_OSD_Name Failed ❌")
            return False

        log_success(f"✔ OSD name read back from the device: {final_name}")
        log_warning(f"OSD name transition: {baseline_name!r} -> {final_name!r}")

        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID10_Set_OSD_Name Passed ✅", elapsed_time))
        return True
    except json.JSONDecodeError:
        # The documented contract boundary, not a speculative guard: utils.send_curl_command
        # promises a RAW string and states that callers run their own json.loads "so that they
        # can distinguish a malformed payload from a missing one". This branch is that
        # distinction, and it is the convention every case in both device-level suites follows.
        log_error("Invalid JSON response")
        log_error("TCID10_Set_OSD_Name Failed ❌")
        return False
