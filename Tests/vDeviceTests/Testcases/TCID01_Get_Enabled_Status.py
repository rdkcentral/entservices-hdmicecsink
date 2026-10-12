"""
/**
 * @file TCID01_Get_Enabled_Status.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID01_Get_Enabled_Status
 * @details Reads the HDMI CEC Sink enabled state over JSON-RPC through
 *          org.rdk.HdmiCecSink.getEnabled and validates the nested result.enabled and
 *          result.success fields of the reply.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable at the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has run and seeded the emulated topology with CEC enabled.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The reply parses as a JSON-RPC response and reports success: true alongside a boolean
 *    enabled.
 *
 * @pass_criteria
 *  - result.success is True, result.enabled is a bool and is True, and run_test() returns
 *    True.
 *
 * @failure_criteria
 *  - Empty or absent response, success not True, enabled missing or not a bool, JSON parse
 *    error, or run_test() returns False.
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

    log_info("Executing the curl command get enabled status")

    # The request is referenced, never rebuilt. HdmiCECSink_Curl.get_enabled is the argv list
    # for org.rdk.HdmiCecSink.getEnabled, and send_curl_command executes it verbatim without a
    # shell. Composing a payload here would fork the transport contract this suite shares.
    curl_response = send_curl_command(HdmiCecSinkApis.get_enabled)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    # send_curl_command reports every transport failure as the byte-exact
    # "< No response from WPEFramework >" sentinel. That string is TRUTHY, so it slips past the
    # guard above; detecting it by prefix is the idiom utils.py documents, and it keeps an
    # unreachable target distinguishable from a malformed payload rather than surfacing as a
    # JSON parse error.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        log_error("TCID01_Get_Enabled_Status Failed ❌")
        return False

    try:
        parsed = json.loads(curl_response)

        # A JSON body that is not an object carries no "result" member to read. Substituting an
        # empty result routes that case through the failure branch below, so run_test() still
        # returns a bool instead of raising AttributeError on a scalar or array reply.
        result = parsed.get("result", {}) if isinstance(parsed, dict) else {}

        # enabled is asserted strictly True, not merely present. SuitManager runs
        # Init_Devicelist_Populate.run_test() before the first case; that module posts
        # Device_Config_Add_Network.yaml and then drives setEnabled(true), and its False return
        # aborts the whole suite. CEC is therefore enabled by the time this read is dispatched,
        # which makes True the only correct observation rather than an assumption.
        if (
            result.get("success") is True
            and isinstance(result.get("enabled"), bool)
            and result.get("enabled") is True
        ):
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID01_Get_Enabled_Status Passed ✅", elapsed_time))
            return True
        else:
            log_warning(f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}")
            log_error("TCID01_Get_Enabled_Status Failed ❌")
            return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID01_Get_Enabled_Status Failed ❌")
        return False
