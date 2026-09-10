"""
/**
 * @file TCID03_Get_OSD_Name.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID03_Get_OSD_Name
 * @details Reads the OSD name the HDMI-CEC Sink plugin publishes for itself over JSON-RPC and
 *          validates the shape of the answer: result.success is True and result.name is a
 *          string. The name that came back is logged rather than compared.
 *
 *          ORDERING, AND WHY NO LITERAL IS ASSERTED. SuitManager.py runs this case at
 *          position 3, among the read-only queries that observe the device before anything
 *          writes to it; TCID10_Set_OSD_Name writes a new name only later, at position 10.
 *          The value read here is therefore the PRE-EXISTING one - the plugin's compiled-in
 *          default until an OSD name has been persisted, and afterwards whatever the last
 *          run of TCID10 left in the CEC settings file, which survives a plugin restart.
 *          Comparing it against a literal would make this case pass or fail on which runs
 *          preceded it, so the assertion is on shape and the observed value goes to the log
 *          where the run record keeps it.
 *
 *          The name belongs to the device under test itself - the sink television at CEC
 *          logical address 0. The peers Init_Devicelist_Populate.py seeds beneath it, the
 *          audio system at logical address 5 included, carry their own OSD names, which are
 *          read through getDeviceList and never through this API.
 *
 * @precondition
 *  - Required plugin is active and reachable via JSON-RPC endpoint.
 *  - Target environment is ready for HDMI CEC emulation/command execution.
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
 *  - getOSDName answers with a result member reporting success and carrying the sink's own
 *    OSD name as a string.
 *
 * @pass_criteria
 *  - result.success is True, result.name is a string, and run_test() returns True.
 *
 * @failure_criteria
 *  - Command dispatch failure, no response from WPEFramework, JSON parsing error, a response
 *    that is not a JSON-RPC object, a missing or non-string name, a success member that is
 *    not True, or run_test() returns False.
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
    '''Read the sink's own OSD name over JSON-RPC and validate the shape of the answer.
    Returns:
        True when the response carries result.success True and a string result.name; False on
        a dispatch failure, the no-response sentinel, an unparsable body, a non-object
        envelope, or a result whose shape does not match.
    '''
    start_time = time.perf_counter()

    log_info("Executing the curl command get OSD name")

    # The command is taken whole from HdmiCECSink_Curl.py. No curl argument and no JSON-RPC
    # payload is assembled here: composing a request is that module's responsibility, and
    # utils.send_curl_command executes the constant as an argv list without a shell.
    curl_response = send_curl_command(HdmiCecSinkApis.get_osd_name)

    if not curl_response:
        log_error("✖ curl command not sent")
        return False

    # send_curl_command reports every transport failure with the TRUTHY sentinel
    # "< No response from WPEFramework >", which the falsy check above cannot catch. utils.py
    # documents startswith("< No response") as the detection idiom. Without this guard an
    # unreachable endpoint would fall through to json.loads and be misreported as a malformed
    # payload rather than as an absent one.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        parsed = json.loads(curl_response)

        # A JSON-RPC answer is an object, but a bare `null`, an array or a scalar are all
        # valid JSON and would arrive here intact - `null` in particular is long enough to
        # survive the length check inside send_curl_command. Normalising both containers
        # before either is subscripted is what keeps every path of this function returning a
        # bool, rather than letting an AttributeError escape into SuitManager's runner.
        envelope = parsed if isinstance(parsed, dict) else {}
        result = envelope.get("result")
        if not isinstance(result, dict):
            result = {}

        # IHdmiCecSink.h declares GetOSDName(string &name, bool &success), so `name` and
        # `success` are exactly the JSON keys. isinstance(..., str) accepts the empty string
        # on purpose: an empty OSD name is a legitimate reading of the device, and rejecting
        # it would be asserting a value.
        observed_name = result.get("name")
        has_success = result.get("success") is True
        has_name = isinstance(observed_name, str)

        # Recorded, never compared - see the ordering note in the file docstring. Logged
        # before the verdict so the value is in the run record even when the shape check
        # fails. repr() keeps an empty or whitespace-only name visible.
        log_info(f"Observed OSD name: {observed_name!r}")

        if has_success and has_name:
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID03_Get_OSD_Name Passed ✅", elapsed_time))
            return True

        log_warning(
            f"Actual  : {json.dumps(parsed, indent=2, sort_keys=True)}"
        )
        log_error("TCID03_Get_OSD_Name Failed ❌")
        return False
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID03_Get_OSD_Name Failed ❌")
        return False
