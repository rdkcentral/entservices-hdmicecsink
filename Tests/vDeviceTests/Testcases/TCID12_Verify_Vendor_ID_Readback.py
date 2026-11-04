"""
/**
 * @file TCID12_Verify_Vendor_ID_Readback.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *        Reads back the sink's advertised vendor identifier over JSON-RPC and asserts that a
 *        usable identifier is being reported after the preceding case wrote one.
 *
 * @testcase TCID12_Verify_Vendor_ID_Readback
 * @details Dispatches org.rdk.HdmiCecSink.getVendorId and validates the response shape:
 *          result.success is True and result.vendorid is a non-empty string. The keys are
 *          exactly `vendorid` and `success`, per IHdmiCecSink.h
 *          GetVendorId(string &vendorid, bool &success); the differently cased `vendorID`
 *          returned by getActiveSource describes a PEER's vendor and is not read here.
 *
 *          CONSUMER OF AN ORDERED PAIR - the one thing to understand before editing this
 *          module. SuitManager.py registers TCID11_Set_Vendor_ID at position 11 and this case
 *          at position 12, and that order is load-bearing rather than cosmetic: TCID11
 *          ESTABLISHES the vendor identifier and this case READS IT BACK. Two consequences
 *          follow, and both are deliberate. This module WRITES NOTHING - it issues a single
 *          read and owns no payload - because writing here would collapse the pair into one
 *          self-confirming test and destroy the ordering evidence that gives the pair its
 *          value. And nothing is restored afterwards, because nothing was changed.
 *
 *          WHAT THIS ADDS OVER TCID04_Get_Vendor_ID, which dispatches the same request. The
 *          two cases are not duplicates; they occupy opposite sides of the suite's first
 *          write. TCID04 runs at position 4, inside the read-only block, and observes the
 *          BASELINE identifier - whatever the device already held, a value this suite never
 *          established. This case runs after the write and closes the loop: it is the read
 *          half of a write-then-read-back exchange. Neither call proves anything about the
 *          write on its own; the PAIR is what turns "setVendorId was acknowledged" into
 *          "setVendorId took effect", which is the device-level evidence a single call cannot
 *          produce.
 *
 *          THE EXACT IDENTIFIER IS ASSERTED, and it is imported rather than restated. The value
 *          lives in exactly one place - HdmiCECSink_Curl.SET_VENDOR_ID_VALUE, the same constant
 *          TCID11's request is built from - so the two halves of the pair cannot drift apart, and
 *          a shape-only check is not enough: a non-empty identifier comes back from a device that
 *          ignored the write entirely, which is precisely the outcome the pair exists to exclude.
 *
 *          THE COMPARISON IS ON THE 24-BIT VALUE, NOT ON THE TEXT, because the interface does not
 *          promise a byte-for-byte echo and does not need to. getVendorId returns
 *          appVendorId.toString(), and CECBytes::toString() (hdmicec/ccec/include/ccec/Operands.hpp)
 *          formats each byte with std::hex, no zero padding and no "0x" prefix - so the three
 *          bytes 0x00, 0x19, 0xFB are published as "019fb". Text equality would fail a correct
 *          device for its formatting; int(value, 16) equality is what the two renderings actually
 *          agree on. A value that cannot be parsed as hexadecimal at all is a failure and names
 *          what came back.
 *
 *          Sound in isolation as well as in sequence: run under a name filter without TCID11, the
 *          identifier will not match and this case FAILS rather than passing vacuously - which is
 *          the correct outcome, because the pair's evidence is exactly what is missing then. The
 *          diagnostic says so instead of leaving the next reader to work it out.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint: a device under test -
 *    physical hardware or a QEMU target - hosts org.rdk.HdmiCecSink and answers at
 *    utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate.run_test() has already seeded the CEC topology and left HDMI-CEC
 *    enabled; SuitManager.py runs it once, before the first test case.
 *  - TCID11_Set_Vendor_ID has run at the preceding registration position and written the vendor
 *    identifier this case reads back. TCID11 deliberately does not restore the previous value,
 *    precisely so that it is still in place here.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository. No continuous integration
 *    workflow runs it, none of the prerequisites above is present in a build environment, and
 *    nothing described here has been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py - endpoint resolution and the shell-free curl dispatcher
 *  - HdmiCECSink_Curl.py - the get_vendor_id definition and SET_VENDOR_ID_VALUE, the identifier
 *    TCID11 wrote and this case requires back
 *  - SuitManager.py - registers this case at position 12, immediately after its producer
 *
 * @expected_result
 *  - getVendorId answers with result.success True and a result.vendorid string that denotes the
 *    same 24-bit identifier as HdmiCECSink_Curl.SET_VENDOR_ID_VALUE, confirming that the write
 *    TCID11_Set_Vendor_ID performed took effect rather than merely being acknowledged.
 *
 * @pass_criteria
 *  - result.success is True, result.vendorid is a non-empty string parseable as hexadecimal, its
 *    integer value equals int(HdmiCECSink_Curl.SET_VENDOR_ID_VALUE, 16), and run_test() returns
 *    True.
 *
 * @failure_criteria
 *  - An empty or sentinel response, a JSON parsing error, a missing, non-string or blank
 *    vendorid, a vendorid that is not parseable as hexadecimal, a value that denotes a different
 *    identifier from the one written, a success value other than True, or run_test() returning
 *    False.
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

# The block above is the six-symbol contract every case in this suite is written against, kept
# intact rather than pruned per case so that every module here presents an identical import block
# and an added or dropped helper shows up in a diff.


def _as_vendor_value(text):
    '''Return the 24-bit identifier a published vendorid string denotes, or None.

    The plugin and this suite spell the same identifier differently - "019fb" against "0x0019FB" -
    because CECBytes::toString() emits unpadded hex with no prefix. Both are parsed here as
    hexadecimal so the comparison is made on the value the two spellings share; anything that is
    not hexadecimal at all answers None and is reported as such rather than silently mismatching.
    Args:
        text: A vendorid string, with or without a leading "0x".
    Returns:
        The integer value, or None when the string does not denote one.
    '''
    if not isinstance(text, str) or text.strip() == "":
        return None
    try:
        return int(text.strip(), 16)
    except ValueError:
        return None


def run_test():
    '''Read the vendor identifier back and require it to be the one TCID11 wrote.

    The read half of the ordered pair whose write half is TCID11_Set_Vendor_ID. The expected value
    is imported from the single constant both halves resolve, and the comparison is made on the
    24-bit value rather than on its text, because the two spellings of one identifier differ only
    in padding and prefix.
    Returns:
        True when result.success is True and result.vendorid denotes the written identifier; False
        on a transport failure, a JSON parsing failure, a shape mismatch or a different
        identifier. A bool is returned on every path, which is the contract SuitManager.py binds.
    '''
    start_time = time.perf_counter()

    log_info("Executing the curl command get vendor id for readback verification")

    # THE ONLY REQUEST THIS MODULE MAKES, and it is a read. The value under test was established
    # by TCID11_Set_Vendor_ID at the preceding registration position; this case never writes, so
    # the pair's division of labour - one writer, one reader - stays intact. The constant is
    # dispatched verbatim: HdmiCECSink_Curl.py owns the method name, payload and timeout, and
    # utils.send_curl_command runs it as an argv list with no shell, so nothing is assembled here.
    curl_response = send_curl_command(HdmiCecSinkApis.get_vendor_id)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command reports every transport failure as its byte-exact
    # NO_RESPONSE_SENTINEL, a TRUTHY string that therefore survives the guard above and needs its
    # own test - the prefix check utils.py documents. Without it an unreachable endpoint would be
    # carried into json.loads and misreported as a malformed payload rather than a missing one,
    # which points at the plugin instead of at the absent device.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        parsed = json.loads(curl_response)

        # A JSON-RPC envelope is an object carrying an object-valued "result". Anything else
        # json.loads accepts - a bare list, a scalar, or a non-mapping "result" - has no member
        # to read, so it is normalised to an empty mapping and reported as a shape mismatch below
        # instead of raising AttributeError out of run_test() and breaking the bool-on-every-path
        # contract above.
        result = parsed.get("result") if isinstance(parsed, dict) else None
        if not isinstance(result, dict):
            result = {}

        vendor_id = result.get("vendorid")
        log_info(f"Read-back vendorid: {vendor_id!r}")

        # `is True` rather than a truthy test, so a JSON 1 or "true" cannot pass for a boolean
        # success. The identifier itself is compared on its 24-bit value against the one constant
        # both halves of the pair resolve, which is what turns "setVendorId was acknowledged" into
        # "setVendorId took effect": a non-empty string alone comes back from a device that
        # ignored the write.
        expected_value = _as_vendor_value(HdmiCecSinkApis.SET_VENDOR_ID_VALUE)
        observed_value = _as_vendor_value(vendor_id)

        if (
            result.get("success") is True
            and expected_value is not None
            and observed_value == expected_value
        ):
            log_success(
                f"✔ the advertised identifier denotes 0x{observed_value:06X}, the value "
                "TCID11_Set_Vendor_ID wrote"
            )
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID12_Verify_Vendor_ID_Readback Passed ✅", elapsed_time))
            return True

        log_warning(
            "Expected: result.success True and result.vendorid denoting "
            f"{HdmiCecSinkApis.SET_VENDOR_ID_VALUE} - the identifier TCID11_Set_Vendor_ID writes. "
            "Run without that producer, this case is expected to report a different identifier."
        )
        log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
        log_error("TCID12_Verify_Vendor_ID_Readback Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID12_Verify_Vendor_ID_Readback Failed ❌")
        return False
    # NO RESTORE CLAUSE, and its absence is correct rather than an omission. This module changes
    # nothing - it issues one read - so there is no prior state to put back. No artificial wait is
    # needed either: send_curl_command is synchronous, and the write this case verifies completed
    # in the preceding case. The device is left exactly as it was found for the cases that follow.
