"""
/**
 * @file TCID15_Send_Standby_Message.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID15_Send_Standby_Message
 * @details Dispatches org.rdk.HdmiCecSink.sendStandbyMessage over JSON-RPC and asserts the whole
 *          acknowledgement envelope rather than merely its success member. The API takes no
 *          parameters and returns nothing but success, so the reply is fully determined and an
 *          equality comparison against the complete envelope is the strictest assertion
 *          available here.
 *
 *          SCOPE - THIS CASE VERSUS TCID25. This is the plain single-API precursor: one request,
 *          one acknowledgement, no frame injection and no peer observation.
 *          TCID25_Standby_Coordination_Flow owns the multi-step variant, re-exercising the same
 *          command inside a coordinated flow driven by its own fixtures. The two are therefore
 *          not redundant, and SuitManager.py encodes the same split in its declared order:
 *          10-16 are the single-API writes, 17-27 the multi-message flows.
 *
 *          RESIDUAL STATE, DECLARED RATHER THAN REPAIRED. sendStandbyMessage broadcasts CEC
 *          Standby, so it may leave the emulated peers powered down after this case returns, and
 *          the sink's command surface publishes no inverse to undo that - the nearest method,
 *          SendAudioDevicePowerOnMessage, only requests System Audio Mode. This case therefore
 *          cannot restore what it changed and does not pretend to. Whether that residual affects a
 *          later case has NOT been observed: the argument recorded at the close of run_test() is
 *          that each later case re-establishes its own preconditions through its own vComponent
 *          posts, which is a reading of those modules rather than a measurement of a run.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable at the JSON-RPC endpoint utils.py
 *    resolves, with HDMI-CEC enabled on the device under test.
 *  - Init_Devicelist_Populate has run as the suite initialization module and seeded the emulated
 *    source-role peers, so there is a CEC network for the broadcast to reach.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository. No continuous integration workflow
 *    runs it, no service is started on its behalf, and nothing described here has been observed
 *    against a live device or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - OBSERVED BY THIS CASE: the sink accepts the request and answers with a success
 *    acknowledgement. That acknowledgement is the whole of what this transport reports.
 *  - INTENDED, NOT OBSERVED: the acknowledged request makes the sink emit CEC <Standby> onto the
 *    bus toward its peers. A one-shot curl request/response cannot see a bus frame, and no
 *    published method reports one, so nothing below asserts it and this case must not be read as
 *    evidence that the broadcast was sent.
 *
 * @pass_criteria
 *  - The reply equals {"jsonrpc":"2.0","id":42,"result":{"success":true}} exactly and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - An empty reply, the "< No response from WPEFramework >" transport sentinel, an envelope
 *    differing from the expected payload, a JSON parse error, or run_test() returning False.
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

    log_info("Executing the curl command send standby message")

    curl_response = send_curl_command(
        HdmiCecSinkApis.send_standby_message
    )

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # The falsy guard above cannot catch a transport failure by itself: utils.send_curl_command
    # reports one with the TRUTHY sentinel "< No response from WPEFramework >" and publishes
    # response.startswith("< No response") as the way to detect it. Without this second guard an
    # unreachable endpoint would reach json.loads and be reported as a parse error, hiding a dead
    # device behind a malformed-payload message.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework - standby message not acknowledged")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        if json.loads(curl_response) == expected_output_response:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID15_Send_Standby_Message Passed ✅", elapsed_time))
            return True
        else:
            log_error("TCID15_Send_Standby_Message Failed ❌")
            return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID15_Send_Standby_Message Failed ❌")
        return False
    # RESIDUAL STATE: THERE IS NO finally: RESTORE HERE, AND ITS ABSENCE IS DELIBERATE.
    #
    # A restore clause would sit exactly at this position - the source suite's
    # TCID08_Set_Enabled_False puts one here - and there is none because the sink's command
    # surface publishes no inverse of sendStandbyMessage. IHdmiCecSink names a wake only as the
    # inbound NOTIFICATION OnWakeupFromStandby, which the sink raises and no test can call, and
    # the one power-on-shaped method it does publish, SendAudioDevicePowerOnMessage, merely issues
    # a System Audio Mode Request to the audio system - it does not un-standby the peers. Reaching
    # for its constant would therefore be exactly the unrelated setter called as a side door that
    # is refused here, alongside a hand-built payload and a vComponent YAML post smuggled in by
    # widening this module's import set. The limitation is reported rather than forced, which is
    # what this engagement requires of fixture state exactly as it requires of coverage.
    #
    # WHY THE RESIDUAL IS TOLERATED, stated as the reading it is rather than as a measurement: no
    # later module in this suite reads peer power state as an inherited precondition, because each
    # re-establishes what it needs through its own vComponent posts - Device_Setapi_Open_Pass.yaml
    # clears a driver fault, Device_Status.yaml sets a peer's power state explicitly, and
    # Device_Image_View_On.yaml with the active-source fixtures drive wake behaviour where a flow
    # needs it. The source suite orders itself the same way, declaring this same broadcast as its
    # first case with 32 cases after it. Neither suite has been executed here, so this is an
    # argument from the modules' text and not evidence from a run.
