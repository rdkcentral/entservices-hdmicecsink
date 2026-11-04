"""
/**
 * @file TCID14_Set_Latency_Info.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID14_Set_Latency_Info
 * @details Sets the sink's current latency information over JSON-RPC through
 *          org.rdk.HdmiCecSink.setLatencyInfo and asserts the success acknowledgement.
 *          Its four parameters - video latency, low latency mode, audio output
 *          compensated and audio output delay - are carried by the suite's single
 *          definition of them, the HdmiCECSink_Curl.set_latency_info request constant.
 *
 *          SCOPE IS THE OUTBOUND SETTER ONLY. setLatencyInfo makes the sink broadcast a
 *          <Report Current Latency> message for Dynamic Auto LipSync, so the write
 *          direction is all this case exercises. The inbound half - an incoming
 *          <Request Current Latency> and the physical-address comparison deciding whether
 *          the sink answers it - is driven by the sibling fixtures
 *          Device_Request_Current_Latency.yaml (matching address) and
 *          Device_Request_Current_Latency_Mismatch.yaml (non-matching). This case posts
 *          neither, because it imports no vComponent helper.
 *
 *          The sink publishes no latency getter, so the applied values cannot be read
 *          back. The acknowledgement is the whole of what is verified, and nothing
 *          beyond it is inferred.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has seeded the CEC topology for the suite.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The plugin acknowledges the request with {"success": true}.
 *  - The applied latency values are not read back: the sink exposes no getter for them.
 *
 * @pass_criteria
 *  - The reply equals {"jsonrpc":"2.0","id":42,"result":{"success":true}} and run_test()
 *    returns True.
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

    expected_output_response = {
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "success": True
        }
    }

    log_info("Executing the curl command set latency info")

    # The request constant owns all four latency parameter values, so they are not
    # restated here: the payload this case sends is defined in exactly one place.
    curl_response = send_curl_command(HdmiCecSinkApis.set_latency_info)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # utils.send_curl_command signals a transport failure with the
    # "< No response from WPEFramework >" sentinel - a non-empty, TRUTHY string the falsy
    # check above cannot see - so it is tested explicitly rather than parsed as JSON and
    # misreported as a malformed reply.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    # No teardown, deliberately: the latency configuration is left at the deterministic
    # values the request constant encodes. No restore could be confirmed - the sink
    # publishes no latency getter - and no other case in this suite reads that
    # configuration, so writing different values back would only hide the residual state.
    try:
        if json.loads(curl_response) == expected_output_response:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID14_Set_Latency_Info Passed ✅", elapsed_time))
            return True
        else:
            log_error("TCID14_Set_Latency_Info Failed ❌")
            return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID14_Set_Latency_Info Failed ❌")
        return False
