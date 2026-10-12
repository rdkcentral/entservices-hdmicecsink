"""
/**
 * @file TCID04_Get_Vendor_ID.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID04_Get_Vendor_ID
 * @details Reads the sink's own vendor identifier over JSON-RPC
 *          (org.rdk.HdmiCecSink.getVendorId) and validates the response shape:
 *          result.success is True and result.vendorid is a non-empty string. The keys are
 *          exactly `vendorid` and `success`, per IHdmiCecSink.h
 *          GetVendorId(string &vendorid, bool &success); the differently cased `vendorID`
 *          that getActiveSource returns describes a PEER's vendor and is not read here.
 *
 *          BASELINE READ, NOT A COMPARISON - the one thing most easily got wrong here.
 *          SuitManager.py schedules this case at position 4, inside the read-only block that
 *          precedes the suite's first write, so the identifier observed is whatever the
 *          device already holds: a value this suite never established and cannot predict.
 *          No literal is asserted; the shape is asserted and the observed value logged, so
 *          the run's own record shows what the baseline was. The deterministic value belongs
 *          to TCID11_Set_Vendor_ID, which writes it, and TCID12_Verify_Vendor_ID_Readback,
 *          which reads it back; TCID28_Invalid_VendorID_Nochange later compares this field
 *          across a rejected write. A literal at position 4 would fail on any device whose
 *          vendor identifier this suite had simply never set.
 *
 *          Read-only: nothing is written and nothing needs restoring, so the device is left
 *          exactly as it was found for the cases that follow.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint.
 *  - Target environment is ready for HDMI CEC emulation/command execution.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository: no continuous integration
 *    workflow runs it, and nothing described here has been observed against a live device
 *    or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - getVendorId answers with result.success True and a non-empty result.vendorid string.
 *
 * @pass_criteria
 *  - result.success is True, result.vendorid is a string, and run_test() returns True.
 *
 * @failure_criteria
 *  - Command failure, the transport sentinel, a JSON parsing error, a missing or non-string
 *    vendorid, a success value other than True, or run_test() returns False.
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
    '''Read the sink's vendor identifier and validate the shape of the response.

    Shape-only by design: at position 4 the identifier is whatever the device already holds,
    so a literal comparison would assert something this suite never established.
    Returns:
        True when result.success is True and result.vendorid is a non-empty string; False on
        a transport failure, a JSON parsing failure, or a shape mismatch. A bool is returned
        on every path, which is the contract SuitManager.py binds.
    '''
    start_time = time.perf_counter()

    log_info("Executing the curl command get vendor id")

    # Dispatched verbatim: HdmiCECSink_Curl.py owns the method name, payload and timeout, and
    # utils.send_curl_command runs it as an argv list with no shell, so nothing is assembled
    # here.
    curl_response = send_curl_command(HdmiCecSinkApis.get_vendor_id)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command reports every transport failure as its byte-exact
    # NO_RESPONSE_SENTINEL, a TRUTHY string that therefore survives the guard above and needs
    # its own test: without this, an unreachable endpoint would reach json.loads and be
    # misreported as a malformed payload rather than a missing one.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        parsed = json.loads(curl_response)

        # A JSON-RPC envelope is an object carrying an object-valued "result". Anything else
        # json.loads accepts - a bare list, a scalar, or a non-mapping "result" - has no
        # member to read, so it is normalised to an empty mapping and reported as a shape
        # mismatch below instead of raising AttributeError out of run_test().
        result = parsed.get("result") if isinstance(parsed, dict) else None
        if not isinstance(result, dict):
            result = {}

        vendor_id = result.get("vendorid")
        log_info(f"Observed baseline vendorid: {vendor_id!r}")

        # `is True` rather than a truthy test, so a JSON 1 or "true" cannot pass for a boolean
        # success. Non-empty is the strongest honest assertion available here: the plugin
        # renders the identifier from a three-byte VendorID, so an empty string is always a
        # defect, while any particular value is not this case's business.
        if (
            result.get("success") is True
            and isinstance(vendor_id, str)
            and vendor_id != ""
        ):
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID04_Get_Vendor_ID Passed ✅", elapsed_time))
            return True

        log_warning("Expected: result.success True and a non-empty string result.vendorid")
        log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
        log_error("TCID04_Get_Vendor_ID Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID04_Get_Vendor_ID Failed ❌")
        return False
