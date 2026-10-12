"""
/**
 * @file TCID13_Set_Menu_Language.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID13_Set_Menu_Language
 * @details Sets the sink television's menu language through the org.rdk.HdmiCecSink
 *          setMenuLanguage JSON-RPC method and asserts the plugin's success
 *          acknowledgement. This closes the end-to-end leg of the SetMenuLanguage gap:
 *          the API is exercised by the sink's own L2 suite but had no device-level case,
 *          the asymmetry catalogued as the missing sink vDeviceTests suite (rank 22, P1).
 *
 *          WHAT THE SINGLE CALL DRIVES. The implementation stores the supplied language
 *          through setCurrentLanguage() and broadcasts <Set Menu Language> through
 *          sendMenuLanguage(), whose operand is a three-byte ISO 639-2 code because the
 *          middleware Language operand is fixed at three bytes. The case therefore covers
 *          the outbound language path from JSON-RPC parameter to encoded CEC frame. The
 *          mapToIso639_2() converter is NOT claimed: it maps a BCP-47 presentation language
 *          on the INBOUND user-settings path, and setMenuLanguage forwards its parameter
 *          verbatim without traversing it.
 *
 *          CLASSIFICATION: TRANSPORT-ACCEPTANCE PLUS A NO-SIDE-EFFECT INVARIANT, NOT A
 *          WRITE/READ-BACK CASE. The applied language cannot be verified at this level and this
 *          module does not claim otherwise. setCurrentLanguage() stores the value on the sink's own
 *          device entry (HdmiCecSinkImplementation.cpp:2083) and no published JSON-RPC method
 *          exposes it; the <Set Menu Language> broadcast that follows is an OUTBOUND frame, and
 *          this suite's transports cannot read outbound frames - the vComponent API is POST-only,
 *          with no endpoint that reports what the device under test emitted - nor can they receive
 *          plugin events, since a Thunder event subscription needs an HTTP listener that a curl
 *          transport does not have. So two things are asserted, and nothing more is implied: the
 *          acknowledgement envelope, and that the call left the CEC device inventory untouched.
 *          The second is a real regression guard rather than a formality - an implementation that
 *          perturbed the device list while encoding the language would fail it while still
 *          answering success.
 *
 *          WHAT WOULD MAKE THIS A FUNCTIONAL READ-BACK CASE, reported rather than made under AAP
 *          Directive 6: a published getter for the current menu language on
 *          Exchange::IHdmiCecSink, or a vComponent endpoint that reports the frames the device
 *          emitted. Either would let the encoded operand be compared against the request.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is reachable and hosts an
 *    active org.rdk.HdmiCecSink plugin answering JSON-RPC at utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has seeded the emulated CEC topology and left HDMI-CEC
 *    enabled, so the sink holds an allocated logical address: setCurrentLanguage() and
 *    sendMenuLanguage() both return early while the sink is still UNREGISTERED.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository. No continuous integration
 *    workflow runs it, none of the prerequisites above is present in a build environment,
 *    and nothing described here has been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The plugin acknowledges the request with {"success": true} and the CEC device inventory is
 *    identical before and after the call. The applied value is not read back, because the sink
 *    exposes no getter for the menu language.
 *
 * @pass_criteria
 *  - The reply equals {"jsonrpc":"2.0","id":42,"result":{"success":true}}, the device inventory
 *    reads identically before and after, and run_test() returns True.
 *
 * @failure_criteria
 *  - Response mismatch, command failure, an unreadable device inventory on either side of the
 *    call, an inventory that changed across it, JSON parsing error, or testcase returns False.
 */
"""


import time
import json
from utils import (
    send_curl_command,
    device_inventory,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def run_test():
    start_time = time.perf_counter()

    expected_output_response = {
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "success": True
        }
    }

    # Inventory snapshot BEFORE the write, so the invariant below compares two real observations
    # rather than one observation against an assumption. utils.device_inventory is the suite's one
    # reader of the CEC population - it returns (readable, count, frozenset-of-logical-addresses)
    # and refuses every unusable reply, so `readable` False below means "no invariant can be
    # asserted", never "the population is empty".
    inventory_readable, before_count, before_addresses = device_inventory(
        HdmiCecSinkApis.get_device_list
    )

    # The baseline is a PRECONDITION, refused before the write rather than after it. A case that
    # writes first and only then discovers it cannot compare has already perturbed the device it
    # was going to make a claim about, and its verdict would rest on the acknowledgement alone
    # while still reading as though the invariant had been evaluated.
    if not inventory_readable:
        log_error("✖ the device inventory could not be read, so no invariant can be asserted")
        log_error("TCID13_Set_Menu_Language Failed ❌")
        return False
    log_info(f"Device inventory before: {before_count} devices at {before_addresses}")

    log_info("Executing the curl command set menu language")

    # The shared constant is dispatched as-is: the language it carries, the endpoint it
    # targets and its timeout all belong to HdmiCECSink_Curl.py, and composing a payload here
    # would put a second, divergent definition of this request into the suite.
    curl_response = send_curl_command(
        HdmiCecSinkApis.set_menu_language
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # A transport failure arrives as the TRUTHY "< No response from WPEFramework >" sentinel,
    # not as an empty value, so the falsy check above cannot detect it on its own. Without
    # this guard the sentinel would fall through to json.loads and be reported as a parse
    # error - a wrong diagnosis of an unreachable endpoint.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    # RESIDUAL STATE, REPORTED BECAUSE IT CANNOT BE CONFIRMED AWAY. The menu language is left at
    # the value HdmiCECSink_Curl.set_menu_language encodes, so the residual is deterministic: the
    # same value after every run. It is not restored because it cannot be READ - setCurrentLanguage
    # stores it on the sink's own device entry (HdmiCecSinkImplementation.cpp:2083) and no published
    # method exposes it - so a restore could neither pick up the previous value nor confirm that it
    # landed. Writing some other language back would replace one unverifiable residual with another.
    # The gap and the change it needs are recorded in the classification note in the file docstring.
    try:
        if json.loads(curl_response) != expected_output_response:
            log_error("TCID13_Set_Menu_Language Failed ❌")
            return False

        # THE INVARIANT THIS CASE CAN ACTUALLY OBSERVE. setMenuLanguage encodes and broadcasts a
        # frame; it must not disturb the CEC device inventory doing so. Asserting that is not a
        # tautology: an implementation that perturbed the device list while encoding the language -
        # a stray addDevice, a dropped entry, a reset of the poll state - would break it, and the
        # acknowledgement alone would still read green.
        after_readable, after_count, after_addresses = device_inventory(
            HdmiCecSinkApis.get_device_list
        )
        if not after_readable:
            log_error("✖ the device inventory became unreadable after setMenuLanguage")
            log_error("TCID13_Set_Menu_Language Failed ❌")
            return False
        if (after_count, after_addresses) != (before_count, before_addresses):
            log_error(
                f"✖ setMenuLanguage disturbed the device inventory: "
                f"{before_count}/{before_addresses} -> {after_count}/{after_addresses}"
            )
            log_error("TCID13_Set_Menu_Language Failed ❌")
            return False
        log_success(
            f"✔ device inventory unchanged across the call: {after_count} devices at "
            f"{after_addresses}"
        )

        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID13_Set_Menu_Language Passed ✅", elapsed_time))
        return True
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID13_Set_Menu_Language Failed ❌")
        return False
