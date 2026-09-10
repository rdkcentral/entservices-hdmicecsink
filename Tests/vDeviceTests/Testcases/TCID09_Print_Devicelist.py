"""
/**
 * @file TCID09_Print_Devicelist.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID09_Print_Devicelist
 * @details Invokes the sink plugin's printDeviceList diagnostic over JSON-RPC and validates
 *          the acknowledgement it returns. printDeviceList is a developer helper: the plugin
 *          walks its CEC device list and emits each present device's parameters - logical
 *          address, device type, physical address, OSD name, vendor ID, CEC version and the
 *          per-field update flags - into the PLUGIN LOG. None of that text is carried in the
 *          JSON-RPC reply, and this suite's curl transport reaches only the reply, so THE DUMP
 *          CONTENT IS NOT ASSERTED HERE: the case verifies that the request is accepted and
 *          acknowledged with both documented result members, and nothing further. Confirming
 *          what the dump contains needs the device log, which is out of reach at this level.
 *
 *          The case is read only: one request, no plugin state altered and nothing to
 *          restore, which is why it belongs in the suite's leading read-only block, ahead of
 *          the first write case.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint.
 *  - Target environment is ready for HDMI CEC emulation/command execution.
 *  - The suite's initialization module has seeded the CEC device list, so the dump walks real
 *    peers - the audio system at logical address 5 among them - rather than an empty list. An
 *    empty list is still acknowledged, so this case does not require the seeding to have
 *    succeeded; it only becomes a meaningful exercise of the per-device dump once it has.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The plugin acknowledges the request, returning "printed" and "success" in its result.
 *  - The dump itself lands in the plugin log and is not inspected by this testcase.
 *
 * @pass_criteria
 *  - result.success is True, result.printed is exactly True, and run_test() returns True.
 *    PrintDeviceList assigns both members true unconditionally
 *    (HdmiCecSinkImplementation.cpp:1446-1452), so True is the only value either can legally
 *    carry and requiring it is a measured claim rather than an optimistic one.
 *
 * @failure_criteria
 *  - An empty or sentinel response, a body that is not a JSON object, success not True, printed
 *    missing or anything other than True, a JSON parsing error, or run_test() returns False.
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


def run_test():
    start_time = time.perf_counter()

    log_info("Executing the curl command print device list")

    curl_response = send_curl_command(
        HdmiCecSinkApis.print_device_list
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # A transport failure comes back as a TRUTHY sentinel string, which the guard above cannot
    # catch; utils.py documents this startswith form as how callers are to detect it.
    if curl_response.startswith("< No response"):
        log_error("✖ curl command sent but WPEFramework returned no response")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        actual_output_response = json.loads(curl_response)
        result = actual_output_response.get("result", {})
        # The default only applies when the member is ABSENT, so a reply carrying
        # "result": null - or an error envelope with a non-object result - would leave a
        # non-dict here and turn the lookups below into an AttributeError escaping run_test.
        # Normalising the shape keeps a malformed reply a reported verdict rather than a
        # raised exception, which is what makes the bool-on-every-path guarantee literal.
        if not isinstance(result, dict):
            result = {}
        has_success = result.get("success") is True

        # BOTH MEMBERS ARE REQUIRED TO BE EXACTLY True, and that is a measured claim rather than
        # an optimistic one. HdmiCecSinkImplementation::PrintDeviceList
        # (HdmiCecSinkImplementation.cpp:1446-1452) calls printDeviceList() and then assigns
        # `printed = true; success = true;` unconditionally, with no branch that can produce
        # anything else and no early return in front of them. So on this API `printed` has exactly
        # one legal value, and False - or a missing member, or a non-boolean - can only mean the
        # reply is not the reply this method produces.
        #
        # An earlier revision type-asserted it instead, reasoning that the flag "is reported even
        # when the device list holds no present device, so a True value would attest to nothing".
        # That is true of what the flag MEANS and irrelevant to what it must BE: accepting False
        # for a field production cannot set to False turns the only falsifiable half of this
        # single-API case into a shape check, and a plugin that regressed the member to False
        # would have passed.
        printed_flag = result.get("printed")
        has_printed_flag = printed_flag is True
        log_info(f"Reported printed flag: {printed_flag}")
        if not has_printed_flag:
            log_error(
                "✖ printDeviceList reported printed="
                f"{sanitise_for_log(printed_flag, max_chars=64)}; PrintDeviceList assigns it "
                "true unconditionally (HdmiCecSinkImplementation.cpp:1448), so any other value "
                "means this is not that method's reply"
            )

        if has_success and has_printed_flag:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID09_Print_Devicelist Passed ✅", elapsed_time))
            return True

        log_warning(
            f"Actual  : {json.dumps(actual_output_response, indent=2, sort_keys=True)}"
        )
        log_error("TCID09_Print_Devicelist Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID09_Print_Devicelist Failed ❌")
        return False
