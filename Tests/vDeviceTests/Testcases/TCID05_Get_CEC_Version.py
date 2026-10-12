"""
/**
 * @file TCID05_Get_CEC_Version.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID05_Get_CEC_Version
 * @details Exercises the sink's CEC-version surface where that surface is observable - on the
 *          emulated CEC bus and in the published device list - because the plugin publishes no
 *          getCecVersion JSON-RPC method. HdmiCECSink_Curl.py records the evidence for that and
 *          therefore carries no command constant for it. Three steps:
 *            1. a DIRECTED <Get CEC Version> from the audio system at logical address 5 is
 *               injected (Device_Get_CEC_Version.yaml, payload 0x50 0x9F). Directed framing is
 *               the only framing HdmiCecSinkProcessor::process(const GetCECVersion &, const
 *               Header &) accepts - it returns early when the destination is BROADCAST - so this
 *               is the framing that reaches the sink's own responder;
 *            2. a DIRECTED <CEC Version> carrying operand 0x05 from the same peer is injected
 *               (Device_CEC_Version.yaml, payload 0x50 0x9E 0x05). HdmiCecSinkProcessor::process
 *               (const CECVersion &, const Header &) calls addDevice(5) and then
 *               deviceList[5].update(msg.version), which is the only path that records a peer's
 *               CEC version;
 *            3. org.rdk.HdmiCecSink.getDeviceList is polled until address 5's entry reports the
 *               version that operand denotes. GetDeviceList publishes it as the entry's
 *               "cecVersion" member, rendered by Version::toString(), and that renderer maps
 *               operand 0x05 to the exact string "Version 1.4"
 *               (hdmicec/ccec/include/ccec/Operands.hpp, class Version).
 *
 *          THE VERDICT IS AN EXACT VALUE, not a shape. The version read back is not the device's
 *          own capability - which is provisioned and may legitimately be 1.4 or 2.0 - but the
 *          value this case itself injected as an operand, so pinning it is a derived assertion
 *          rather than an assumption about the environment. The sink's response to step 1 travels
 *          on the bus rather than in a JSON-RPC reply, so its DELIVERY is asserted (the
 *          vComponent must accept the document) and its content is not claimed; step 2 carries
 *          the verdict.
 *
 *          IDEMPOTENT BY CONSTRUCTION, which is what lets a case that writes to the bus sit
 *          inside the suite's opening observation block. Init_Devicelist_Populate.py already
 *          seeds the same peer, the same opcode and the same operand, and process(CECVersion)
 *          re-enters addDevice() for an address that is already present, so positions 06 through
 *          09 observe exactly the device they would have observed without this case. Nothing else
 *          is written and nothing has to be restored.
 *
 *          BLOCKED, AND REPORTED RATHER THAN MADE: a JSON-RPC reader for the sink's OWN CEC
 *          version would need a getCecVersion declaration on Exchange::IHdmiCecSink so
 *          ThunderTools generates the binding, plus a plugin implementation so Register()
 *          publishes it. Both are production changes, which AAP Directive 6 requires be reported
 *          instead. The sink L1 suite's HdmiCecSinkInitializedEventDsTest.getCecVersion has the
 *          same cause: it is enabled and passing, but it asserts the dispatcher's REFUSAL of the
 *          name rather than a read-back, for exactly the reason above. This module neither
 *          repairs that blocker nor claims to.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint.
 *  - The vComponent HTTP API is reachable, so the two CEC documents below can be injected.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA audio
 *    system at CEC logical address 5 - the peer both injected frames come from.
 *  - AUTHORED, NOT EXECUTED in this repository: no CI workflow runs this suite, and nothing
 *    described here has been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py - endpoint resolution, the shell-free curl dispatcher and the vComponent poster
 *  - HdmiCECSink_Curl.py - the get_device_list command definition
 *  - SuitManager.py - registers this case at position 5 and runs it
 *  - vcomponent_configurations/commands/Device_Get_CEC_Version.yaml
 *  - vcomponent_configurations/commands/Device_CEC_Version.yaml
 *
 * @expected_result
 *  - Both CEC documents are accepted by the vComponent (HTTP 200), so both frames reach the bus.
 *  - org.rdk.HdmiCecSink.getDeviceList answers with result.success True and a deviceList entry
 *    for logical address 5 whose cecVersion is exactly "Version 1.4", the rendering of the
 *    operand injected in step 2.
 *
 * @pass_criteria
 *  - Both vComponent posts return HTTP 200; getDeviceList answers with result.success True; the
 *    deviceList carries an entry for logical address 5; that entry's cecVersion equals
 *    "Version 1.4"; and run_test() returns True.
 *
 * @failure_criteria
 *  - Either vComponent post returns anything other than HTTP 200 - which would leave this case
 *    claiming a bus exchange it never made - getDeviceList is not dispatched, the reply is the
 *    no-response sentinel, the body is not a JSON-RPC envelope carrying an object result,
 *    result.success is not True, address 5 is absent from the deviceList, its cecVersion is
 *    missing or is any other value, a JSON parsing error occurs, or run_test() returns False.
 */
"""


import time
import json

from utils import (
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
    CEC_FRAME_PACING_SECONDS,
)
import HdmiCECSink_Curl as HdmiCecSinkApis


# The peer both frames come from. Address 5 is the audio system in this suite's topology, and it
# is the address Init_Devicelist_Populate seeds a CEC version for, which is what makes step 2 an
# idempotent repetition rather than a new device.
AUDIO_SYSTEM_LOGICAL_ADDRESS = 5

# The two documents, and the single reason they are the directed pair rather than the broadcast
# one: process(GetCECVersion) returns early on a BROADCAST destination, and a frame the emulator
# accepts but the plugin discards would leave this case green having exercised nothing.
GET_CEC_VERSION_YAML = "Device_Get_CEC_Version.yaml"      # 0x50 0x9F      - from 5, directed to 0
CEC_VERSION_YAML = "Device_CEC_Version.yaml"              # 0x50 0x9E 0x05 - from 5, directed to 0

# The expected readback, derived from the operand this case injects rather than from the device.
# Version::toString() (hdmicec/ccec/include/ccec/Operands.hpp) maps the one operand byte through a
# name table, so 0x05 (V_1_4) renders as "Version 1.4" - with the word, and not as "1.4".
CEC_VERSION_OPERAND = 0x05
EXPECTED_CEC_VERSION = "Version 1.4"

# Bounded budget for the readback. A poll interval is the gap between two observations, never a
# duration anything waits for: the loop leaves on the first reading that satisfies it and reports
# what it last saw when the budget expires.
READBACK_TIMEOUT_SECONDS = 10.0
READBACK_POLL_SECONDS = 0.25


def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command and report whether it was accepted.

    HTTP 200 is the only acceptance, and utils.send_vcomponent_command is fail-closed about it: a
    missing document, a refused path, a curl failure and the "applied the YAML then closed the
    connection without answering" case all arrive here as code 0 rather than being laundered into
    a synthetic 200. The body is logged verbatim and never parsed, because on those paths it
    carries curl's diagnosis rather than a response document.
    Args:
        yaml_file: Document name relative to the suite's command fixture directory.
    Returns:
        True only when the vComponent answered HTTP 200.
    """
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A refusal carries "error" instead of "result", and a malformed body could carry a non-object
    result or not be an object at all. Every such case collapses to {} so the caller reports a
    missing field instead of raising AttributeError out of run_test(). A body that is not JSON at
    all still raises json.JSONDecodeError, which run_test() handles as the documented failure.
    Args:
        response_text: Raw response string as returned by utils.send_curl_command.
    Returns:
        The "result" mapping when the body is a JSON object carrying one, otherwise {}.
    """
    body = json.loads(response_text)
    if not isinstance(body, dict):
        return {}
    result = body.get("result")
    return result if isinstance(result, dict) else {}


def _device_entry(result, logical_address):
    """Return the deviceList entry for one logical address, or None when it is absent."""
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return None
    for device in device_list:
        if isinstance(device, dict) and device.get("logicalAddress") == logical_address:
            return device
    return None


def _await_recorded_version():
    """Poll getDeviceList until address 5 reports the injected version, bounded.

    Returns the LAST sample rather than only a verdict, so a failure can report the value that
    was actually present instead of only that the expected one was missing.
    Returns:
        A (settled, entry, detail) triple: whether the expected version was observed, the peer's
        last observed entry (or None), and a diagnostic naming what the last reading contained.
    """
    deadline = time.time() + READBACK_TIMEOUT_SECONDS
    entry = None
    detail = "getDeviceList was never read"
    while True:
        response = send_curl_command(HdmiCecSinkApis.get_device_list)
        if not response:
            detail = "getDeviceList was not dispatched"
        elif response.startswith("< No response"):
            detail = "getDeviceList got no response from WPEFramework"
        else:
            result = _result_object(response)
            if result.get("success") is not True:
                detail = f"getDeviceList did not report success; body={response!r}"
            else:
                entry = _device_entry(result, AUDIO_SYSTEM_LOGICAL_ADDRESS)
                if entry is None:
                    detail = (
                        f"logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} is absent from the "
                        f"device list; body={response!r}"
                    )
                else:
                    observed = entry.get("cecVersion")
                    if observed == EXPECTED_CEC_VERSION:
                        log_warning(f"  device list: {sanitise_for_log(response, max_chars=2048)}")
                        return True, entry, f"cecVersion {observed!r}"
                    detail = (
                        f"address {AUDIO_SYSTEM_LOGICAL_ADDRESS} reports cecVersion "
                        f"{sanitise_for_log(observed, max_chars=64)}, not "
                        f"{EXPECTED_CEC_VERSION!r}"
                    )
        if time.time() >= deadline:
            return False, entry, detail
        time.sleep(READBACK_POLL_SECONDS)


def run_test():
    start_time = time.perf_counter()

    log_info(
        "Injecting a directed <Get CEC Version> and a directed <CEC Version> from logical "
        f"address {AUDIO_SYSTEM_LOGICAL_ADDRESS}, then reading the recorded version back"
    )

    if not _post_hdmicec(GET_CEC_VERSION_YAML):
        log_error(
            f"✖ {GET_CEC_VERSION_YAML} was not accepted by the vComponent, so the sink's "
            "<Get CEC Version> responder was never reached"
        )
        log_error("TCID05_Get_CEC_Version Failed ❌")
        return False
    log_success("✔ directed <Get CEC Version> injected")

    # Inter-frame pacing, the one timed construct here: the bus carries no per-frame observable
    # that could be polled instead, and the two frames are read by two different handlers.
    time.sleep(CEC_FRAME_PACING_SECONDS)

    if not _post_hdmicec(CEC_VERSION_YAML):
        log_error(
            f"✖ {CEC_VERSION_YAML} was not accepted by the vComponent, so no version was "
            "presented to process(CECVersion) and there is nothing to read back"
        )
        log_error("TCID05_Get_CEC_Version Failed ❌")
        return False
    log_success(f"✔ directed <CEC Version> injected (operand 0x{CEC_VERSION_OPERAND:02X})")

    try:
        settled, entry, detail = _await_recorded_version()
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID05_Get_CEC_Version Failed ❌")
        return False

    if not settled:
        log_error(
            f"✖ the injected CEC version was not recorded within {READBACK_TIMEOUT_SECONDS:.0f} s "
            f"- {detail}"
        )
        log_error("TCID05_Get_CEC_Version Failed ❌")
        return False

    log_info(
        f"Address {AUDIO_SYSTEM_LOGICAL_ADDRESS} reports {detail}, matching the injected operand"
    )
    log_warning(f"Peer entry: {json.dumps(entry, indent=2, sort_keys=True)}")
    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID05_Get_CEC_Version Passed ✅", elapsed_time))
    return True
