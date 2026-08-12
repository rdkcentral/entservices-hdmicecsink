"""
/**
 * @file TCID22_System_Audio_Mode_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID22_System_Audio_Mode_Flow
 * @details Drives BOTH VALUE BRANCHES of the <Set System Audio Mode> exchange, which is what
 *          separates this module from the read-only audio cases earlier in the suite: the
 *          JSON-RPC call makes the sink ASK the audio system to power on, and the two injected
 *          fixtures then supply that audio system's ON and OFF announcements in turn. Five
 *          steps, in this order:
 *            1. before-probe - org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus, read for
 *               context and logged beside the after-probe rather than asserted;
 *            2. OUTBOUND SOLICITATION - org.rdk.HdmiCecSink.sendAudioDevicePowerOnMessage, which
 *               calls systemAudioModeRequest() (HdmiCecSinkImplementation.cpp:1636) and directs
 *               <System Audio Mode Request> at CEC logical address 5, the audio system
 *               (smConnection->sendTo(LogicalAddress::AUDIO_SYSTEM, ...) at :1259);
 *            3. INBOUND ANNOUNCEMENT, ON - Device_Set_System_Audio_Mode.yaml injects
 *               <Set System Audio Mode> with operand 0x01, reaching
 *               HdmiCecSinkProcessor::process(const SetSystemAudioMode&, const Header&) at
 *               HdmiCecSinkImplementation.cpp:551 and, through it, the ON arm of
 *               Process_SetSystemAudioMode_msg at :1150;
 *            4. INBOUND ANNOUNCEMENT, OFF - Device_Set_System_Audio_Mode_Off.yaml injects the
 *               same opcode with operand 0x00, reaching the OPPOSITE arm at :1162;
 *            5. after-probe - the same connected-status read, logged beside the first.
 *
 *          WHY BOTH VALUES. The two arms are genuinely asymmetric in the handler, so covering
 *          one does not cover the other: the ON arm notifies only when the panel is powered on
 *          and otherwise logs "Not notifying system audio mode ON event" (:1150-1161), whereas
 *          the OFF arm notifies unconditionally and additionally calls stopArc() when ARC is
 *          still in the initiated state (:1141-1148). The emulator supplies only the ON value by
 *          itself - the active table in
 *          vcomponent_configurations/hdmicec/hdmicec_vcomponent_cec_responses.yaml carries the row
 *          <System Audio Mode Request> -> <Set System Audio Mode> [0x01] - so step 3 makes
 *          the ON arm deterministic rather than dependent on that table, and step 4 covers the
 *          arm the emulated peer never produces at all.
 *
 *          WHY IN THIS ORDER. The OFF injection is posted LAST deliberately and the two must not
 *          be swapped: OFF is the quiescent announcement for an audio system, so ending on it
 *          undoes the transient ON state this module itself provoked and leaves the device under
 *          test as the next testcase expects to find it.
 *
 *          Both fixtures are directed FROM logical address 5 (payload header 0x50: initiator 5,
 *          destination 0), which is the only correct origin for this message - the CEC
 *          specification assigns an audio system exactly one logical address, and only an audio
 *          system announces its system audio mode. Do not substitute a broadcast fixture or a
 *          non-audio initiator. The audio peer is supplied by the emulated topology; the device
 *          under test is never reconfigured to act as its own audio system.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with
 *    the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA
 *    AudioSystem peer at CEC logical address 5, and has left HDMI-CEC enabled. Both parts
 *    matter here: without the peer there is nothing for the solicitation to reach, and
 *    Process_SetSystemAudioMode_msg returns early while cecSettingEnabled is not true
 *    (HdmiCecSinkImplementation.cpp:1133-1137), which would discard both injections.
 *  - The vComponent HTTP API is reachable, so the two announcement payloads can be injected.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - sendAudioDevicePowerOnMessage acknowledges the solicitation, and both announcement
 *    payloads are injected and accepted by the emulator.
 *  - THE HANDLER'S EFFECT IS NOT ASSERTED, because it is not observable from this transport.
 *    The interface publishes no system-audio-mode getter at all - its seven getters are
 *    GetActiveRoute, GetActiveSource, GetAudioDeviceConnectedStatus, GetDeviceList, GetEnabled,
 *    GetOSDName and GetVendorId (IHdmiCecSink.h:191-235) - and the one channel that does carry
 *    the mode, the setSystemAudioModeEvent notification (IHdmiCecSink.h:145-147), is delivered
 *    to registered COM-RPC/JSON-RPC subscribers rather than to a curl request/response. This
 *    module therefore reports what it can honestly observe: that the solicitation was
 *    acknowledged, that both injections were accepted, and that the connected-status probe
 *    still answers with a well-formed body afterwards.
 *
 * @pass_criteria
 *  - Both required YAML posts return HTTP 200, sendAudioDevicePowerOnMessage acknowledges
 *    result.success as True, getEnabled reports enabled True BEFORE either announcement is
 *    injected - Process_SetSystemAudioMode_msg returns immediately when cecSettingEnabled is not
 *    true, so this is what makes the two injections meaningful rather than merely accepted - the
 *    after-probe parses with result.success True and a boolean result.connected, and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - A request is not dispatched, a response is the no-response sentinel, either required
 *    vComponent post does not return HTTP 200, the solicitation does not acknowledge success,
 *    getEnabled does not answer or reports enabled other than True - in which case both
 *    announcements would have been posted successfully and then discarded before either arm of the
 *    handler ran - the after-probe reports success other than True or a non-boolean connected, a
 *    JSON parsing error occurs, or run_test() returns False.
 */
"""

import time
import json

from utils import (
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    CEC_FRAME_PACING_SECONDS,
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


def run_test():
    start_time = time.perf_counter()

    # SHARED STATE: neutralised by the ORDER of the two injections rather than by a restore
    # step. This module announces system audio mode ON and then OFF, and OFF is the quiescent
    # announcement, so the device under test is left in the state a later testcase expects
    # instead of carrying a transient ON announcement forward. That is why step 4 must follow
    # step 3 and not precede it. Nothing else here is persistent: the solicitation only puts a
    # <System Audio Mode Request> on the bus, and the connected-status probes are pure reads.

    # Before-probe: context for the exchange, logged rather than asserted.
    before = send_curl_command(HdmiCecSinkApis.get_audio_device_connected_status)
    if not before:
        log_error("✖ initial getAudioDeviceConnectedStatus command not sent")
        return False
    # The transport failure guard that actually fires in this suite. utils.send_curl_command
    # returns the "< No response from WPEFramework >" sentinel - a TRUTHY string - for every
    # failure mode, so the falsy check above cannot catch one on its own. The prefix form is the
    # detection contract utils.py documents for callers.
    if before.startswith("< No response"):
        log_error("✖ initial getAudioDeviceConnectedStatus returned no response")
        return False
    log_warning(f"Initial audio connection: {before}")

    # ACT 1 - OUTBOUND SOLICITATION. The sink asks the audio system to power on; see @details
    # step 2. This precedes both injections because the announcements below are the audio
    # system's answer to it, and an announcement injected first would be unsolicited traffic
    # rather than half of an exchange.
    curl_response = send_curl_command(HdmiCecSinkApis.send_audio_device_power_on_message)
    if not curl_response:
        log_error("✖ sendAudioDevicePowerOnMessage command not sent")
        return False
    if curl_response.startswith("< No response"):
        log_error("✖ sendAudioDevicePowerOnMessage returned no response from WPEFramework")
        return False
    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    # THE GUARD THAT WOULD DISCARD BOTH INJECTIONS IS CHECKED BEFORE THEY ARE MADE.
    # Process_SetSystemAudioMode_msg opens on `if (cecSettingEnabled != true) return;`
    # (HdmiCecSinkImplementation.cpp:1133-1137), so with CEC disabled both frames below are
    # accepted by the emulator, both posts return HTTP 200, and the handler discards each one
    # before either arm is reached. Nothing downstream can tell that apart from a run in which the
    # arms executed, because neither arm leaves a reading behind - so without this check the case
    # could pass having exercised precisely nothing. TCID23 and TCID24 guard their own
    # solicitations the same way and for the same reason.
    enabled_probe = send_curl_command(HdmiCecSinkApis.get_enabled)
    if not enabled_probe or enabled_probe.startswith("< No response"):
        log_error("✖ getEnabled did not answer, so the handler's own guard cannot be confirmed open")
        return False
    try:
        enabled_now = _result_object(enabled_probe).get("enabled")
    except json.JSONDecodeError:
        log_error("✖ getEnabled reply is not valid JSON")
        return False
    if enabled_now is not True:
        log_error(
            f"✖ HDMI-CEC reads enabled={enabled_now!r}. Process_SetSystemAudioMode_msg returns "
            "immediately when cecSettingEnabled is not true, so both announcements below would be "
            "posted successfully and then discarded, and neither arm of the handler would run"
        )
        return False
    log_success("✔ HDMI-CEC is enabled, so the handler will not discard the announcements")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # ACT 2 - INBOUND ANNOUNCEMENT, ON VALUE. Device_Set_System_Audio_Mode.yaml carries payload
    # ["0x50","0x72","0x01"]: directed from logical address 5 to 0, opcode 0x72
    # (<Set System Audio Mode>), then the single [System Audio Status] operand 0x01, which the
    # implementation spells SYSTEM_AUDIO_MODE_ON (HdmiCecSinkImplementation.cpp:61). Neither
    # fixture name may be altered: naming a document that does not exist would make
    # send_vcomponent_command return (0, "YAML file not found: ..."), silently skipping the
    # injection, which is why both posts' results are required below rather than discarded.
    ok_on = _post_hdmicec("Device_Set_System_Audio_Mode.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # ACT 3 - INBOUND ANNOUNCEMENT, OFF VALUE. The same opcode with operand 0x00
    # (SYSTEM_AUDIO_MODE_OFF, :62) reaches the opposite arm of the handler, which the emulator's
    # auto-response table never produces on its own. Posted last, so the module ends on the
    # quiescent announcement; see the shared-state note above.
    ok_off = _post_hdmicec("Device_Set_System_Audio_Mode_Off.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    if not (ok_on and ok_off):
        log_error("✖ required vComponent emulation posts failed")
        return False

    # After-probe: the same read as the before-probe, so the pair can be compared in the log.
    after = send_curl_command(HdmiCecSinkApis.get_audio_device_connected_status)
    if not after:
        log_error("✖ final getAudioDeviceConnectedStatus command not sent")
        return False
    if after.startswith("< No response"):
        log_error("✖ final getAudioDeviceConnectedStatus returned no response")
        return False
    log_warning(f"Final audio connection: {after}")

    # ONE try COVERS EVERY PARSE IN THIS MODULE: the solicitation's acknowledgement and both
    # probe bodies are read inside the block below, so a single json.JSONDecodeError handler
    # keeps the contract of returning a bool on every path rather than raising into
    # SuitManager's runner. The TRANSPORT guards stay inline at each step above, because "no
    # reply arrived" and "a reply arrived and was not JSON" are different verdicts.
    try:
        # Act 1's acknowledgement. SendAudioDevicePowerOnMessage publishes exactly one field -
        # success (IHdmiCecSink.h:256) - and the implementation sets it unconditionally after
        # dispatching the request (HdmiCecSinkImplementation.cpp:1636-1641), so requiring True
        # is a measured claim and is the only claim the solicitation itself supports.
        if _result_object(curl_response).get("success") is not True:
            log_error("✖ sendAudioDevicePowerOnMessage did not acknowledge success")
            return False

        before_result = _result_object(before)
        after_result = _result_object(after)
        connected_before = before_result.get("connected")
        connected_after = after_result.get("connected")
        log_info(
            "Observed audio device connected state: "
            f"before={connected_before} after={connected_after}"
        )

        # TYPE-ONLY ASSERTION ON `connected` - DO NOT STRENGTHEN THIS INTO A VALUE CHECK.
        # Neither True nor False is a claim this testcase can honestly make. The flag mirrors
        # HdmiCecSinkImplementation::getAudioDeviceConnectedStatus (:1331), which reports whether
        # a peer was DISCOVERED at logical address 5 - not whether system audio mode was
        # announced - and the sink's own L2 suite asserts the counter-intuitive value for that
        # reason: EXPECT_FALSE(connected) in ../../L2Tests/tests/HdmiCecSink_L2Test.cpp
        # GetAudioDeviceConnectedStatus_COMRPC and EXPECT_FALSE(result["connected"].Boolean()) in
        # GetAudioDeviceConnectedStatus_JSONRPC, because
        # no audio system is ever discovered in that in-process host. This suite has never been
        # executed, so pinning the value would fail in one valid environment or the other, and
        # the OFF announcement posted last deliberately undoes the transient ON state anyway.
        # `success` is different: the implementation sets it unconditionally (:1334), so
        # requiring True is measured.
        if after_result.get("success") is True and isinstance(connected_after, bool):
            elapsed_time = time.perf_counter() - start_time
            log_success(log_with_timing("TCID22_System_Audio_Mode_Flow Passed ✅", elapsed_time))
            return True

        log_warning(f"Actual  : {after}")
    except json.JSONDecodeError:
        log_error("Invalid JSON response")

    log_error("TCID22_System_Audio_Mode_Flow Failed ❌")
    return False
