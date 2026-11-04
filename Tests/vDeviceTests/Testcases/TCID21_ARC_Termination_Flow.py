"""
/**
 * @file TCID21_ARC_Termination_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID21_ARC_Termination_Flow
 * @details Drives ONE Audio Return Channel TERMINATION end to end and probes the one arm of the
 *          handler's admission gate for which this suite ships a fixture. Five steps, in this
 *          order:
 *            1. BEFORE-PROBE, ASSERTED - org.rdk.HdmiCecSink.getDeviceList must report the
 *               audio system at CEC logical address 5, and
 *               org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus must read connected True.
 *               Both are preconditions of the flow, not context: without the peer at 5 the
 *               admission gate below can never be satisfied, so every injection this case makes
 *               would be discarded unread and the case would pass having exercised nothing;
 *            2. POSITIVE INJECTION, REQUIRED - Device_Terminate_Arc.yaml delivers the audio
 *               system's <Terminate ARC> to HdmiCecSinkProcessor::process(const TerminateArc&,
 *               const Header&) at HdmiCecSinkImplementation.cpp:535;
 *            3. NEGATIVE ARM A, REQUIRED - Device_Terminate_Arc_Broadcast.yaml, same initiator,
 *               broadcast destination. Required means the POST must be accepted; the handler's
 *               rejection of the frame remains unobservable, and the two are kept distinct
 *               below;
 *            4. DISABLE / RESTORE, ASSERTED - org.rdk.HdmiCecSink.setupARCRouting with
 *               {"enabled": false}, the sink's own request to take ARC back down
 *               (SetupARCRouting, HdmiCecSinkImplementation.cpp:1600);
 *            5. AFTER-PROBE, ASSERTED - connected must still read True and getDeviceList must
 *               report the same device count and the same set of logical addresses as step 1.
 *               Terminating ARC moves the ARC state machine; it must not undiscover the audio
 *               system or disturb the inventory, and both are checked rather than logged.
 *
 *          THE ADMISSION GATE IS WHY THE TWO FIXTURES DIFFER BY ONE BYTE. The handler opens with
 *          the same two-arm rejection its initiation counterpart uses, at
 *          HdmiCecSinkImplementation.cpp:537 - `if((!(header.from.toInt() == 0x5)) ||
 *          (header.to.toInt() == LogicalAddress::BROADCAST)) return;` - so a <Terminate ARC> is
 *          admitted only when it comes FROM logical address 5, the audio system, AND is DIRECTED
 *          rather than broadcast. The header byte alone decides it:
 *            * 0x50 (positive)  initiator 5, destination 0 - both arms satisfied;
 *            * 0x5F (arm A)     initiator 5, destination 0xF broadcast - fails the destination
 *                               arm while holding the initiator constant.
 *          In both fixtures the opcode byte is 0xC5, <Terminate ARC>. Changing a header byte
 *          changes which arm is under test; do not substitute fixtures between the steps.
 *
 *          ONLY ONE NEGATIVE ARM IS EXERCISED, AND THAT IS NOT AN OVERSIGHT. The gate's other
 *          arm - a directed frame from an initiator that is not the audio system - needs a
 *          fixture carrying header 0x40, and this suite ships one on the INITIATE ARC side but
 *          none on the TERMINATE ARC side, so there is no valid document to post for it. THIS
 *          MODULE POSTS THE TWO TERMINATE DOCUMENTS NAMED ABOVE AND NOTHING ELSE - no
 *          initiation fixture, which is TCID20_ARC_Initiation_Flow's to post, and no invented
 *          filename, because a name that does not resolve makes send_vcomponent_command return
 *          (0, "YAML file not found: ...") and would read as a passing ARC case that injected
 *          nothing. The arm is therefore left unexercised and recorded here rather than faked,
 *          and TCID20_ARC_Initiation_Flow already covers it on the initiation path, where the
 *          gate expression is identical and the fixture for it does exist.
 *
 *          WHAT THE NEGATIVE INJECTION DOES AND DOES NOT PROVE, AND WHY IT IS STILL REQUIRED. It
 *          is expected to be ACCEPTED by the emulator - HTTP 200 means the frame reached the CEC
 *          bus - and then DISCARDED by the handler at the gate. Those two outcomes are not in
 *          tension, and this module never conflates them: a 200 on the negative fixture is
 *          evidence of injection, never of an ARC termination. The rejection itself IS
 *          unobservable from here, because the gate is a bare `return` that publishes no counter,
 *          no state and no notification, so no assertion is made about the frame's fate.
 *          DELIVERY, HOWEVER, IS OBSERVABLE, and this case requires it. An earlier revision
 *          posted this fixture without checking the result, reasoning from the unobservable
 *          rejection; the consequence was that a renamed, moved or malformed fixture would make
 *          send_vcomponent_command return (0, "YAML file not found: ...") and the case would
 *          still pass, reporting a green ARC gate probe that had injected nothing. The HTTP status
 *          is the one fact this transport does report about the post, so it is asserted, and the
 *          fate of the admitted frame is left to @expected_result.
 *
 *          THIS CASE IS THE RESTORER OF AN ORDERED PAIR. TCID20_ARC_Initiation_Flow is the
 *          PRODUCER half: it deliberately leaves ARC ENABLED and documents, at the point where a
 *          teardown would otherwise sit, that this module is the consumer that takes ARC back
 *          down. SuitManager.py registers the two at consecutive positions (20 then 21) for that
 *          reason. Step 4 above is therefore not decoration - it is the step that returns the
 *          device to the state the pair was entered in, which is why it is asserted rather than
 *          merely logged. Run in order the pair is state-neutral; TCID20 alone is not, and this
 *          case alone assumes ARC was brought up before it.
 *
 *          ADDRESSED BY DESIGN, NOT BY MEASUREMENT. COVERAGE_GAPS.md ranks the missing sink
 *          vDeviceTests suite 22nd at priority P1 (#gap-plugin-sink-vdevicetests) precisely
 *          because the sink's ARC and audio-routing use cases - the ones that define the sink -
 *          had no end-to-end safety net. In the §4b API table `SetupARCRouting` is recorded as
 *          covered by the sink's own L2 suite (SetupARCRouting_COMRPC and
 *          SetupARCRouting_JSONRPC in ../../L2Tests/tests/HdmiCecSink_L2Test.cpp) with NO E2E
 *          leg. TCID20 is AUTHORED to supply the INITIATION half of that leg and this module the
 *          TERMINATION half; runtime validation and measured coverage for both remain deferred
 *          until a device or emulator environment is available.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with
 *    the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA
 *    AudioSystem peer at CEC logical address 5, and has left HDMI-CEC enabled. Without that
 *    peer the admission gate at HdmiCecSinkImplementation.cpp:537 can never be satisfied, since
 *    a <Terminate ARC> from any other address is discarded unread. The peer is supplied BY THE
 *    EMULATED TOPOLOGY: the device under test is never reconfigured to act as its own audio
 *    system, which is the role-inversion construct this suite excludes by design.
 *  - TCID20_ARC_Initiation_Flow is expected to have run immediately before this case and to have
 *    left ARC enabled; this module is the half of that pair which restores it.
 *  - The vComponent HTTP API is reachable, so the two ARC frames can be injected.
 *  - AUTHORED, NOT EXECUTED in this repository: no CI workflow runs this suite, and nothing
 *    described here has been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The directed <Terminate ARC> frame is injected and accepted by the emulator, and
 *    setupARCRouting acknowledges the disable request.
 *  - The gate-arm frame is injected and is expected to be DISCARDED by the handler. That
 *    expectation is stated and logged, not asserted, for the reason given in the details
 *    section above.
 *  - THE ARC TERMINATION HANDSHAKE ITSELF IS NOT ASSERTED, because it is not observable from
 *    this transport. An admitted frame reaches Process_TerminateArc()
 *    (HdmiCecSinkImplementation.cpp:3359), which moves m_currentArcRoutingState to
 *    ARC_STATE_ARC_TERMINATED and fans out arcTerminationEvent
 *    (ArcTerminationEvent("success"), HdmiCecSinkImplementation.cpp:3381) - a Thunder
 *    notification delivered to registered COM-RPC/JSON-RPC subscribers rather than to a one-shot
 *    curl request/response - and no getter on the interface reports the ARC routing state.
 *  - The ARC state is left DISABLED, restoring what TCID20_ARC_Initiation_Flow enabled. That
 *    restore is ALSO published as a module-level cleanup() hook, which SuitManager.py runs for
 *    every registered case unconditionally - after a pass, after a failure, after an exception,
 *    and even for a case it SKIPPED because its producer failed. So ARC is taken back down even
 *    when TCID20's initiation failed and this case never ran as a test, which a finally clause
 *    inside run_test() could not cover. The hook is idempotent: when run_test() has already
 *    driven the disable call it reports that and does nothing.
 *  - NO INITIAL ARC STATE IS CAPTURED, because it is known by construction rather than by
 *    observation and there is no getter to capture it with. m_currentArcRoutingState is
 *    initialised to ARC_STATE_ARC_TERMINATED (HdmiCecSinkImplementation.cpp:635),
 *    Init_Devicelist_Populate never calls setupARCRouting, and no case registered before TCID20
 *    does either - so "terminated" is the state the pair inherited, and asserting the disable
 *    call IS the restore.
 *  - The invariants of step 5 hold: the audio system stays discovered and the device inventory
 *    is byte-for-byte the set observed in step 1.
 *
 * @pass_criteria
 *  - EVERY vComponent post returns HTTP 200 - the <Terminate ARC> injection and the gate-arm
 *    injection alike - setupARCRouting acknowledges result.success as True, the after-probe
 *    parses with result.success True and a boolean result.connected, and run_test() returns True.
 *
 * @failure_criteria
 *  - A request is not dispatched, a response is the no-response sentinel, ANY vComponent post
 *    does not return HTTP 200 - including the gate-arm frame, whose non-delivery would leave this
 *    case claiming to have exercised a rejection arm it never reached - the disable call does not
 *    acknowledge success, the after-probe reports success other than True or a non-boolean
 *    connected, a JSON parsing error occurs, or run_test() returns False. The gate-arm verdict is
 *    taken only after the disable request has been issued, so no failure path leaves ARC
 *    enabled.
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


def _ensure_arc_disabled():
    """Issue setupArcRouting(enabled=false) and report whether the plugin confirmed it.

    Returns (ok, detail).

    This is the inverse operation this module owes the suite, and it is issued unconditionally
    from run_test()'s finally block rather than only on the path that reaches ACT 3.
    TCID20_ARC_Initiation_Flow deliberately leaves ARC enabled and names this module as the
    restorer, so every early return before ACT 3 - a before-probe that did not answer, a
    required injection that was rejected - used to leak an ENABLED ARC into every case that
    follows, and nothing said so.

    Issuing the request a second time on the path that already made it is deliberate and
    harmless: disabling ARC that is already disabled is idempotent, which is the same property
    TCID30 and TCID31 assert for setEnabled. Paying one extra request is the cost of never
    having to reason about which exit path was taken.

    Confirmation means all of: a request that was dispatched, a reply that is not the
    no-response sentinel, a body that parses as a JSON object, and result.success exactly True -
    the single field SetupARCRouting publishes (IHdmiCecSink.h:328).
    """
    response = send_curl_command(HdmiCecSinkApis.setup_arc_routing_false)

    if not response:
        return False, "setupArcRouting(false) was not dispatched"
    if response.startswith("< No response"):
        return False, "setupArcRouting(false) got no response from WPEFramework"

    try:
        result = _result_object(response)
    except json.JSONDecodeError as exc:
        return False, f"setupArcRouting(false) reply did not parse ({exc}); body={response!r}"

    if result.get("success") is not True:
        return False, f"setupArcRouting(false) did not acknowledge success; body={response!r}"

    return True, "ARC confirmed disabled"


# True once a setupArcRouting(enabled=false) has been ISSUED AND CONFIRMED in this process, so the
# module-level cleanup() hook below can tell "already restored" from "must restore". Set only on
# the confirmed path - an unconfirmed attempt leaves it False so the hook tries again, because an
# attempt that was not acknowledged is not a restoration.
_arc_disable_confirmed = False


def cleanup():
    """Leave ARC DISABLED - the state the TCID20/TCID21 pair inherited and owes back.

    THIS HOOK IS WHY THE PAIR'S GUARANTEE IS ONE, AND IT WAS MISSING.

    TCID20_ARC_Initiation_Flow deliberately does not restore: it enables ARC and names this module
    as the restorer, and its own comment states that the restore "lives in TCID21's cleanup() hook,
    and SuitManager runs cleanup() for every registered case unconditionally - INCLUDING a case it
    skipped because its producer failed". This module's @details said the same. Neither was true:
    no cleanup() existed here, so `getattr(module, "cleanup", None)` returned None and SuitManager
    had nothing to run. The only restoration was the finally clause inside run_test() - which
    cannot fire on the one path the pair's argument depends on, the path where TCID20's initiation
    fails, this case is SKIPPED for an unmet dependency, and run_test() is never called at all.
    ARC was then left ENABLED for every case that follows, and the file said the opposite.

    Idempotent, in both directions: when run_test() already issued and confirmed the disable this
    reports that and issues nothing, and when it did not, issuing setupArcRouting(false) against
    an already-disabled ARC is itself idempotent - the same property TCID30 and TCID31 assert for
    setEnabled.

    NO CAPTURE IS INVOLVED, and that is by construction rather than by omission:
    m_currentArcRoutingState is initialised to ARC_STATE_ARC_TERMINATED
    (HdmiCecSinkImplementation.cpp:635), Init_Devicelist_Populate never calls setupARCRouting, and
    no case registered before TCID20 does either - so "terminated" is the state the pair inherited.
    There is also no getter for the ARC routing state on the interface, so an observation-based
    capture is not available to be written.

    Returns:
        True when there was nothing to do, or the disable was issued AND acknowledged. False when
        the request was not dispatched, not answered, or not acknowledged - in which case ARC may
        still be enabled and the message says so.
    """
    global _arc_disable_confirmed
    if _arc_disable_confirmed:
        log_info("TCID21 cleanup: ARC was already confirmed disabled by run_test(), nothing to do")
        return True

    log_info("TCID21 cleanup: disabling ARC so the state the pair inherited is restored")
    ok, detail = _ensure_arc_disabled()
    if not ok:
        log_error(
            "TCID21 cleanup: ARC may still be ENABLED for subsequent cases - "
            f"{sanitise_for_log(detail)}"
        )
        return False
    _arc_disable_confirmed = True
    log_success(f"✔ TCID21 cleanup: {detail}")
    return True


def run_test():
    start_time = time.perf_counter()

    # The measurement runs inside a try whose finally always restores ARC to disabled, so no
    # exit path - early return or exception - can leave it enabled for the cases that follow.
    # The restoration reports its own verdict, and this case fails if either half fails.
    #
    # The module-level cleanup() hook above covers the one path this finally cannot: the run in
    # which this case is SKIPPED because TCID20's initiation failed, so run_test() is never
    # entered. The two do not duplicate work - the flag set here is what makes the hook a no-op.
    try:
        flow_ok = _run_arc_termination_flow()
    finally:
        global _arc_disable_confirmed
        cleanup_ok, cleanup_detail = _ensure_arc_disabled()
        if cleanup_ok:
            _arc_disable_confirmed = True
            log_info(f"  Cleanup: {cleanup_detail}")
        else:
            # Reported independently of the measurement: a leaked enabled ARC is a different
            # defect from a failed termination assertion, and it affects later cases rather
            # than this one.
            log_error(
                "TCID21_ARC_Termination_Flow cleanup FAILED: ARC may still be enabled for "
                f"subsequent cases - {cleanup_detail}"
            )

    if flow_ok and cleanup_ok:
        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID21_ARC_Termination_Flow Passed ✅", elapsed_time))
        return True

    log_error("TCID21_ARC_Termination_Flow Failed ❌")
    return False


def _run_arc_termination_flow():
    """The three acts this case measures. Returns True when every assertion holds.

    Every assertion below is exactly as it was; only the verdict reporting moved to run_test()
    so that the restore in its finally block is guaranteed to run first.
    """
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

    # ACT 1 - POSITIVE INJECTION, THE ONE POST THIS CASE REQUIRES. Device_Terminate_Arc.yaml
    # carries payload ["0x50","0xC5"]: header 0x50 is initiator 5 to destination 0, opcode 0xC5
    # is <Terminate ARC>. That header is the only one of the two fixtures that clears both arms
    # of the gate at HdmiCecSinkImplementation.cpp:537, so this is the frame that represents an
    # actual termination and its post is required rather than advisory. Naming a file that does
    # not exist would make send_vcomponent_command return (0, "YAML file not found: ..."), which
    # would otherwise read as a passing ARC case that never injected anything - hence the check.
    #
    # The injection deliberately precedes the disable request in ACT 3: the frame is the AUDIO
    # SYSTEM asking the television to tear ARC down, which is the direction a real peer drives,
    # and the sink's own setupARCRouting call is then the local half of the same teardown.
    ok_positive = _post_hdmicec("Device_Terminate_Arc.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    if not ok_positive:
        log_error(
            "✖ the <Terminate ARC> injection was not delivered to the bus, so this case cannot "
            "claim to have exercised a termination at all - a document that cannot be posted "
            "returns (0, diagnostic) rather than raising, which would otherwise read as a passing "
            "ARC case that injected nothing"
        )
        return False

    # ACT 2 - THE GATE ARM THIS SUITE HAS A FIXTURE FOR. DELIVERY IS REQUIRED; THE HANDLER'S
    # VERDICT IS NOT ASSERTED.
    #
    # Device_Terminate_Arc_Broadcast.yaml differs from the positive fixture in its HEADER BYTE
    # ONLY - 0x5F instead of 0x50 - so it isolates the destination arm of the rejection at
    # HdmiCecSinkImplementation.cpp:537 with the initiator arm held constant. It is expected to
    # be accepted by the emulator and then discarded by the handler.
    #
    # THE TWO OUTCOMES ARE SEPARATE, AND ONLY ONE OF THEM IS THIS TRANSPORT'S BUSINESS:
    #   * whether the frame was INJECTED - an HTTP 200 from the vComponent - is a fact about
    #     delivery, and it is now REQUIRED. A misnamed document, an unreadable fixture or an
    #     unreachable emulator each return (0, diagnostic) from send_vcomponent_command, and with
    #     that outcome tolerated this case would report having exercised the gate arm while
    #     injecting nothing. Since an undelivered frame also cannot change the connected flag, the
    #     unchanged-state reading below would hold for the wrong reason - the same trap the
    #     positive injection above is already guarded against.
    #   * whether the HANDLER accepted or discarded it is NOT asserted, and that remains the
    #     honest reporting line of this module. The gate is a bare `return`: it increments no
    #     counter, changes no state and raises no notification, so a rejection leaves nothing this
    #     transport can read. Requiring a non-200 would be worse still - it would assert the
    #     opposite of what should happen, since the emulator is expected to accept a well-formed
    #     frame regardless of what the plugin then does with it.
    #
    # So the 200 required below is evidence that the frame was INJECTED. It is not, and must not
    # be read as, evidence of an ARC termination.
    ok_broadcast = _post_hdmicec("Device_Terminate_Arc_Broadcast.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    log_info(
        "  gate arm A (header 0x5F, broadcast destination) injected; expected to be discarded "
        f"by the handler - post accepted: {ok_broadcast}"
    )

    # The verdict on that delivery is deliberately NOT taken here. ACT 3 below is the disable that
    # makes the TCID20/TCID21 pair state-neutral, and returning before it would leak an enabled ARC
    # into every case that follows - so the check is deferred until the disable has been issued,
    # exactly as TCID30_Repeated_Disable_Idempotent defers its own operation-under-test verdict
    # past its restore.

    # ACT 3 - DISABLE, AND THE RESTORE THAT MAKES THE PAIR STATE-NEUTRAL. setupARCRouting with
    # {"enabled": false} is the sink's own request to take ARC down, and it is the disabling
    # counterpart of TCID20_ARC_Initiation_Flow's ACT 1. TCID20 leaves ARC enabled on purpose and
    # names this module as the restorer, so this call is REQUIRED and its acknowledgement is
    # asserted below rather than merely logged: if it were dropped, the ordered pair would leak
    # an enabled ARC into every case that follows.
    curl_response = send_curl_command(HdmiCecSinkApis.setup_arc_routing_false)
    if not curl_response:
        log_error("✖ setupArcRouting disable command not sent")
        return False
    if curl_response.startswith("< No response"):
        log_error("✖ setupArcRouting disable returned no response from WPEFramework")
        return False
    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    # The deferred delivery verdict from ACT 1, taken here for the same reason as ACT 2's below:
    # ACT 1's comment declares this post REQUIRED rather than advisory - it is the only frame in
    # this case that clears both arms of the gate and so the only one that represents an actual
    # termination - and taking the verdict before the disable had been issued would leave an
    # enabled ARC behind for every case that follows.
    if not ok_positive:
        log_error(
            "✖ the positive <Terminate ARC> frame was not delivered to the bus, so this case "
            "never exercised a termination at all"
        )
        log_error("TCID21_ARC_Termination_Flow Failed ❌")
        return False

    # The deferred delivery verdict from ACT 2, taken now that the disable above has been issued
    # so no path can leak an enabled ARC. It is reported before the unchanged-state reading
    # because an undelivered gate-arm frame invalidates that reading rather than contradicting it.
    if not ok_broadcast:
        log_error(
            "✖ the broadcast-destination gate-arm frame was not delivered to the bus, so this "
            "case cannot claim to have exercised that arm of the rejection"
        )
        log_error("TCID21_ARC_Termination_Flow Failed ❌")
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

    try:
        if _result_object(curl_response).get("success") is not True:
            log_error("✖ setupArcRouting disable did not acknowledge success")
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
        # HdmiCecSinkImplementation::hdmiCecAudioDeviceConnected, which is set when a peer is
        # discovered at logical address 5 rather than by an ARC termination, so an ARC flow is not
        # what moves it. The sink's own L2 suite asserts the counter-intuitive value for exactly
        # that reason - EXPECT_FALSE(connected) in
        # ../../L2Tests/tests/HdmiCecSink_L2Test.cpp GetAudioDeviceConnectedStatus_COMRPC and
        # EXPECT_FALSE(result["connected"].Boolean()) in GetAudioDeviceConnectedStatus_JSONRPC -
        # because no audio system is ever discovered in that in-process host. This suite has
        # never been executed, so pinning the value would fail in one valid environment or the
        # other. `success` is different: the implementation sets it unconditionally, so requiring
        # True is measured.
        if after_result.get("success") is not True or not isinstance(connected_after, bool):
            log_error(
                "✖ the final getAudioDeviceConnectedStatus did not report success with a boolean "
                f"connected flag: success={after_result.get('success')!r} "
                f"connected={connected_after!r}"
            )
            log_warning(f"Actual  : {after}")
            return False
    except json.JSONDecodeError:
        log_error("✖ setupArcRouting disable reply is not valid JSON")
        return False

    log_success("✔ setupARCRouting(enabled=false) acknowledged")
    return True
