"""
/**
 * @file TCID23_Short_Audio_Descriptor_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID23_Short_Audio_Descriptor_Flow
 * @details Exercises BOTH DIRECTIONS of one Short Audio Descriptor (SAD) exchange, which is
 *          what separates this module from the read-only cases earlier in the suite: the
 *          JSON-RPC call makes the sink ASK, and the injected fixture supplies the audio
 *          system's REPLY. Four steps, in this order:
 *            1. BEFORE-PROBE, ALL THREE PARTS ASSERTED - org.rdk.HdmiCecSink.getEnabled must
 *               read enabled True, org.rdk.HdmiCecSink.getDeviceList must report the audio
 *               system at CEC logical address 5, and
 *               org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus must read connected True.
 *               All three are preconditions rather than context: with CEC disabled
 *               requestShortaudioDescriptor returns without putting anything on the bus
 *               (HdmiCecSinkImplementation.cpp:2170-2175), and with no peer at address 5 the
 *               solicitation has no recipient and the injected reply no legitimate origin;
 *            2. OUTBOUND SOLICITATION - org.rdk.HdmiCecSink.requestShortAudioDescriptor, which
 *               encodes <Request Short Audio Descriptor> and directs it at CEC logical address
 *               5 (HdmiCecSinkImplementation.cpp:2204 sends to LogicalAddress::AUDIO_SYSTEM);
 *            3. INBOUND REPLY - Device_Report_Short_Audio_Descriptor.yaml injects the audio
 *               system's <Report Short Audio Descriptor> answer, reaching
 *               HdmiCecSinkProcessor::process(const ReportShortAudioDescriptor&, const Header&)
 *               at HdmiCecSinkImplementation.cpp:545;
 *            4. AFTER-PROBE, ASSERTED - CEC must still be enabled, the audio system must still
 *               read connected, and getDeviceList must report the same device count and the same
 *               set of logical addresses as step 1. A descriptor exchange carries capability
 *               information; it must not disable HDMI-CEC, undiscover the peer or alter the
 *               topology.
 *
 *          THE ORDER OF STEPS 2 AND 3 IS FUNCTIONAL, NOT COSMETIC, and must not be swapped: a
 *          reply injected before its request is an unsolicited report, not half of an exchange.
 *
 *          WHY THE REPLY IS INJECTED EVEN THOUGH THE EMULATOR WOULD ANSWER. The auto-response
 *          table in vcomponent_configurations/hdmicec/hdmicec_vcomponent_cec_responses.yaml DOES
 *          carry the <Request Short Audio Descriptor> -> <Report Short Audio Descriptor> pair,
 *          but it carries it with `payload: null`: the emulator answers with the opcode and no
 *          operands. A Short Audio Descriptor IS its operands - three bytes per descriptor - and
 *          Process_ShortAudioDescriptor_msg reads them, so an operand-less auto-reply exercises
 *          the handler's entry and nothing it does. The user_defined payload injected here
 *          carries a real one-descriptor body, which is what makes step 3 an exchange with
 *          content rather than an empty acknowledgement.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with
 *    the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA
 *    AudioSystem peer at CEC logical address 5, and has left HDMI-CEC enabled.
 *  - The vComponent HTTP API is reachable, so the reply payload can be injected.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - requestShortAudioDescriptor acknowledges the solicitation, and the descriptor reply is
 *    injected and accepted by the emulator.
 *  - THE DECODED DESCRIPTOR CONTENTS ARE NOT ASSERTED, AND THIS CASE IS CLASSIFIED
 *    ACCORDINGLY: it is an INJECTION-AND-INVARIANT case, not an effect-observing one.
 *    RequestShortAudioDescriptor publishes only a success flag (IHdmiCecSink.h:251), no getter
 *    on the interface returns the received descriptors, and Process_ShortAudioDescriptor_msg
 *    stores nothing at all - it decodes the operands straight into a JsonArray and hands them to
 *    Send_ShortAudioDescriptor_Event (HdmiCecSinkImplementation.cpp:1078-1100, event at :1062),
 *    a Thunder notification that reaches registered COM-RPC/JSON-RPC subscribers rather than a
 *    one-shot curl request/response. There is consequently no state anywhere for this transport
 *    to read back, which is a stronger statement than "not asserted here".
 *    REQUIRED PRODUCTION CHANGE TO CLOSE THIS GAP, reported and not made: either a
 *    GetShortAudioDescriptors getter on Exchange::IHdmiCecSink that returns the last descriptors
 *    received, or a vComponent endpoint reporting frames the device under test EMITTED so the
 *    outbound <Request Short Audio Descriptor> of step 2 could be observed. Neither exists, and
 *    this suite may not add either.
 *  - WHAT IS ASSERTED INSTEAD IS NOT LIVENESS. getEnabled reading True before step 2 is the
 *    published fact that the solicitation was actually dispatched: RequestShortAudioDescriptor
 *    sets success = true unconditionally (:2178-2183), whereas requestShortaudioDescriptor()
 *    returns WITHOUT SENDING when cecEnableStatus is not true (:2170-2175), and getEnabled
 *    publishes exactly that flag (:1310). One caveat is recorded rather than glossed: that
 *    routine has a third gate, m_logicalAddressAllocated == UNREGISTERED (:2198-2201), and no
 *    getter publishes the allocated address - GetDeviceList deliberately OMITS the sink's own
 *    entry (:1393). A populated peer inventory is evidence that discovery ran and therefore that
 *    an address was allocated, but it is evidence and not proof, and closing that last gap needs
 *    the same production change named above.
 *
 * @pass_criteria
 *  - The before-probe reports enabled True, the audio system at logical address 5 and connected
 *    True; requestShortAudioDescriptor acknowledges result.success as True; the required YAML
 *    post returns HTTP 200; the after-probe reports enabled True, connected True and the step-1
 *    device count and logical-address set unchanged; and run_test() returns True.
 *
 * @failure_criteria
 *  - CEC reads disabled before or after the exchange, the device inventory cannot be read, the
 *    audio system is absent from it, connected reads anything but True before or after, a request
 *    is not dispatched, a response is the no-response sentinel, the required vComponent post does
 *    not return HTTP 200, the solicitation does not acknowledge success, the inventory changes
 *    across the exchange, a JSON parsing error occurs, or run_test() returns False.
 */
"""

import time
import json

# The eight-symbol utils import below is the shared contract the emulation-driven ("flow")
# testcases in this suite are written against, and every symbol in it now has a call site:
# log_with_timing applies the HDMICEC_TIMING_ENABLED decoration and the pass path routes its
# message through it, which is what retired this module's own local copy of that gate.
from utils import (
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command."""
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could
    carry a non-object "result" or not be an object at all. Every such case collapses to {} so
    the caller reports a MISSING FIELD rather than raising AttributeError out of run_test(). A
    body that is not JSON at all still raises json.JSONDecodeError, which run_test() handles as
    the documented failure. Three call sites share this, which is why it is factored out.
    Args:
        response_text: Raw response string as returned by utils.send_curl_command
    Returns:
        The "result" mapping when the body is a JSON object carrying one, otherwise {}.
    """
    body = json.loads(response_text)
    if not isinstance(body, dict):
        return {}
    result = body.get("result")
    return result if isinstance(result, dict) else {}


# The CEC logical address of an audio system: the destination requestShortaudioDescriptor()
# directs its solicitation at (HdmiCecSinkImplementation.cpp:2204) and the origin the injected
# reply claims. Init_Devicelist_Populate seeds that peer as a precondition of the whole suite.
AUDIO_SYSTEM_LOGICAL_ADDRESS = 5

# Bounded budget for the reachable observations - a poll ceiling, never a duration anything waits
# out. Every wait below returns as soon as the state it is watching agrees.
OBSERVE_TIMEOUT_S = 8.0
OBSERVE_POLL_S = 0.25


def _device_inventory():
    """Return (readable, count, sorted_logical_addresses) from the published getDeviceList method.

    Returns:
        (False, None, None) when the reply cannot be read or does not acknowledge success, so a
        caller reports "unreadable" rather than mistaking it for an empty topology.
    """
    response = send_curl_command(HdmiCecSinkApis.get_device_list)
    if not response or response.startswith("< No response"):
        return False, None, None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return False, None, None
    if result.get("success") is not True:
        return False, None, None
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return False, None, None
    addresses = sorted(
        device["logicalAddress"]
        for device in device_list
        if isinstance(device, dict) and isinstance(device.get("logicalAddress"), int)
    )
    return True, result.get("numberofdevices"), addresses


def _read_flag(argv, field):
    """Read one boolean field out of a published getter, or None when it cannot be read."""
    response = send_curl_command(argv)
    if not response or response.startswith("< No response"):
        return None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return None
    if result.get("success") is not True:
        return None
    value = result.get(field)
    return value if isinstance(value, bool) else None


def _wait_for_flag(argv, field, expected):
    """Poll one boolean getter until it reads `expected`; returns (matched, last_observation).

    Bounded by OBSERVE_TIMEOUT_S on a monotonic clock, and it RETURNS THE LAST READING so the
    caller can distinguish "never became true" from "could not be read at all" - the two have
    different causes and deserve different messages.
    """
    deadline = time.monotonic() + OBSERVE_TIMEOUT_S
    while True:
        observed = _read_flag(argv, field)
        if observed is expected:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(OBSERVE_POLL_S)


def run_test():
    """Drive one Short Audio Descriptor exchange and assert everything this transport can observe.

    WHAT IS AND IS NOT REACHABLE HERE, stated once because it governs every assertion below. The
    handler stores nothing: Process_ShortAudioDescriptor_msg decodes the operands into a JsonArray
    and hands them straight to Send_ShortAudioDescriptor_Event, a Thunder notification a curl
    transport cannot subscribe to, and no getter returns the received descriptors. So the
    descriptor CONTENTS are not merely unasserted here - there is no state for any transport to
    read them back from. @expected_result names the production change that would close that.
    WHAT IS ASSERTED, and why each item is a real claim rather than liveness:
      * getEnabled reads True before the solicitation. RequestShortAudioDescriptor sets
        success = true unconditionally (:2178-2183) while requestShortaudioDescriptor() returns
        WITHOUT SENDING when cecEnableStatus is not true (:2170-2175), so `success` alone cannot
        distinguish "request dispatched" from "request silently dropped"; getEnabled publishes
        exactly that flag (:1310).
      * The audio system is present at logical address 5 and connected reads True - the recipient
        of the solicitation and the claimed origin of the reply.
      * The reply injection is required to be delivered.
      * Afterwards CEC is still enabled, the audio system is still connected and the inventory is
        unchanged.
    Returns:
        True when every assertion above holds; False on any transport failure, refused post,
        unreadable reply or disturbed invariant.
    """
    start_time = time.perf_counter()

    # SHARED STATE: none. A descriptor exchange makes the sink report the audio system's
    # capability information to its subscribers; it writes no member, changes no user-visible
    # setting, and the interface publishes no inverse API that could undo it. The absence of a
    # restore step and of a cleanup() hook is therefore deliberate rather than forgotten, and no
    # later testcase depends on this module having reverted anything.

    # ── BEFORE: three asserted preconditions, not context ───────────────────────────────────────
    enabled_before = _read_flag(HdmiCecSinkApis.get_enabled, "enabled")
    if enabled_before is not True:
        log_error(
            f"✖ getEnabled reads {enabled_before!r}, expected True. With CEC disabled "
            "requestShortaudioDescriptor() returns without putting the solicitation on the bus "
            "(HdmiCecSinkImplementation.cpp:2170-2175), so this case would exercise nothing"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False

    inventory_readable, before_count, before_addresses = _device_inventory()
    if not inventory_readable:
        log_error("✖ the device inventory could not be read before the exchange")
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    if AUDIO_SYSTEM_LOGICAL_ADDRESS not in before_addresses:
        log_error(
            f"✖ no audio system at logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} in "
            f"{before_addresses} - the solicitation would have no recipient and the injected "
            "reply no legitimate origin"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False

    # VALUE ASSERTION ON `connected`, NOT A TYPE ASSERTION, and the distinction from the sink's L2
    # suite is the reason. That suite asserts EXPECT_FALSE(connected) in
    # GetAudioDeviceConnectedStatus_COMRPC and GetAudioDeviceConnectedStatus_JSONRPC
    # (../../L2Tests/tests/HdmiCecSink_L2Test.cpp) because its in-process host discovers no audio
    # system at all. THAT DOES NOT TRANSFER HERE: this suite REQUIRES the YAMAHA audio system at
    # logical address 5 as a @precondition, addDevice() sets hdmiCecAudioDeviceConnected
    # unconditionally for that address, and nothing on any path this module drives clears it. True
    # is therefore the expectation for THIS environment, and a type-only check would accept the
    # peer silently vanishing mid-exchange.
    connected_before = _read_flag(HdmiCecSinkApis.get_audio_device_connected_status, "connected")
    if connected_before is not True:
        log_error(
            f"✖ audio device connected reads {connected_before!r} before the exchange, expected "
            f"True with the peer present at logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS}"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    log_info(
        f"Before: CEC enabled, {before_count} devices at {before_addresses}, audio connected=True"
    )

    # ── ACT 1 - OUTBOUND SOLICITATION ──────────────────────────────────────────────────────────
    # The sink asks the audio system for its descriptors. This must precede the injection below;
    # see @details.
    curl_response = send_curl_command(HdmiCecSinkApis.request_short_audio_descriptor)
    if not curl_response:
        log_error("✖ requestShortAudioDescriptor command not sent")
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    # The transport failure guard that actually fires in this suite. utils.send_curl_command
    # returns the "< No response from WPEFramework >" sentinel - a TRUTHY string - for every
    # failure mode, so a falsy check cannot catch one on its own. The prefix form is the detection
    # contract utils.py documents for callers.
    if curl_response.startswith("< No response"):
        log_error("✖ requestShortAudioDescriptor returned no response from WPEFramework")
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    log_warning(f"Response: {curl_response}")
    try:
        if _result_object(curl_response).get("success") is not True:
            log_error("✖ requestShortAudioDescriptor did not acknowledge success")
            log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
            return False
    except json.JSONDecodeError:
        log_error("✖ requestShortAudioDescriptor reply is not valid JSON")
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    log_success("✔ requestShortAudioDescriptor acknowledged, and CEC was enabled when it ran")

    # ── ACT 2 - INBOUND REPLY, REQUIRED ────────────────────────────────────────────────────────
    # Device_Report_Short_Audio_Descriptor.yaml carries payload ["0x50","0xA3","0x01","0x00",
    # "0x00"]: directed from logical address 5 to 0, opcode 0xA3 (<Report Short Audio
    # Descriptor>), then EXACTLY THREE operand bytes forming one descriptor. That width is
    # load-bearing, not arbitrary - ShortAudioDescriptor is a fixed three-byte operand
    # (Operands.hpp:695, MAX_LEN = 3) and the decoding constructor derives its count by INTEGER
    # division, numberofdescriptor = frame.length() / 3 (Messages.hpp:538), reading each
    # descriptor at startPos + i*3. Trimming a byte truncates that count to zero and the handler
    # then observes an empty list, so do not add or remove operand bytes and do not substitute a
    # broadcast fixture. This is also the ONLY fixture for opcode 0xA3 under
    # vcomponent_configurations/commands/ - there is deliberately no Process_-prefixed variant -
    # and naming a file that does not exist makes send_vcomponent_command return
    # (0, "YAML file not found: ..."), which is why the post's result is required.
    if not _post_hdmicec("Device_Report_Short_Audio_Descriptor.yaml"):
        log_error(
            "✖ required injection refused - the audio system's descriptor reply was never "
            "delivered (Device_Report_Short_Audio_Descriptor.yaml)"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    log_success("✔ delivered the audio system's <Report Short Audio Descriptor> reply")

    # ── AFTER: the invariants the exchange must preserve ────────────────────────────────────────
    # Regression guards with teeth rather than formalities: a capability exchange must not disable
    # HDMI-CEC, undiscover the audio system or disturb the topology. Each is polled on a bounded
    # monotonic budget so a slow handler is waited for and a broken one is still reported.
    enabled_ok, enabled_after = _wait_for_flag(HdmiCecSinkApis.get_enabled, "enabled", True)
    if not enabled_ok:
        log_error(
            f"✖ getEnabled reads {enabled_after!r} after the exchange, expected True - a "
            "descriptor exchange must not disable HDMI-CEC"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False

    connected_ok, connected_after = _wait_for_flag(
        HdmiCecSinkApis.get_audio_device_connected_status, "connected", True
    )
    if not connected_ok:
        log_error(
            f"✖ audio device connected reads {connected_after!r} after the exchange, expected "
            "True - a descriptor exchange must not undiscover the audio system"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False

    after_readable, after_count, after_addresses = _device_inventory()
    if not after_readable:
        log_error("✖ the device inventory became unreadable after the exchange")
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    if (after_count, after_addresses) != (before_count, before_addresses):
        log_error(
            f"✖ the exchange disturbed the device inventory: "
            f"{before_count}/{before_addresses} -> {after_count}/{after_addresses}"
        )
        log_error("TCID23_Short_Audio_Descriptor_Flow Failed ❌")
        return False
    log_success(
        f"✔ invariants hold: CEC enabled, {after_count} devices at {after_addresses}, "
        "audio connected=True"
    )

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID23_Short_Audio_Descriptor_Flow Passed ✅", elapsed_time))
    return True
