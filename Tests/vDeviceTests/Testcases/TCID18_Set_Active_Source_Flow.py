"""
/**
 * @file TCID18_Set_Active_Source_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID18_Set_Active_Source_Flow
 * @details Drives the sink's SET-ACTIVE-SOURCE flow end to end and validates the active source
 *          the device reports after EACH step, rather than only once at the end. Four steps, in
 *          order:
 *
 *            1. a before-probe of org.rdk.HdmiCecSink.getActiveSource, recording whatever
 *               active source the device already holds;
 *            2. a broadcast <Active Source> injection so a peer holds the source - probed and
 *               asserted, which is what makes step 3 a transition rather than a reading;
 *            3. org.rdk.HdmiCecSink.setActiveSource over JSON-RPC, which asks the sink to take
 *               the active source itself and takes no parameters - probed and asserted;
 *            4. a directed <Inactive Source> injection from a peer that is NOT the active
 *               source - probed and asserted to have changed nothing.
 *
 *          THE STEPS ARE ORDERED AND PROBED SEPARATELY BECAUSE THAT IS THE ONLY WAY THE SETTER
 *          IS ACTUALLY TESTED. The earlier arrangement called setActiveSource first and then
 *          injected two frames, one of which - the broadcast announcement - overwrites exactly
 *          the state the setter had just established. Whatever the setter did was gone before
 *          anything was read, so the case asserted only the SHAPE of the final reply and a
 *          plugin whose setActiveSource did nothing at all would have passed. Injecting the
 *          announcement FIRST and calling the setter SECOND makes the setter the last writer,
 *          and its effect observable.
 *
 *          EVERY EXPECTED VALUE IS DERIVED FROM THE PRODUCTION PATH, not chosen:
 *            - step 2 posts ["0x4F","0x82","0x30","0x00"] - broadcast <Active Source> from
 *              logical address 4 announcing 3.0.0.0. process(ActiveSource) calls addDevice(4)
 *              then updateActiveSource(4, msg), which sets deviceList[4].update(3.0.0.0) and
 *              m_currentActiveSource = 4 because 4 differs from the television's own allocated
 *              address (HdmiCecSinkImplementation.cpp:159-160, :2150-2159). GetActiveSource then
 *              reports logical address 4 at "3.0.0.0" on port "HDMI2", the port string being
 *              "HDMI" followed by the first address nibble minus one (cpp:1344-1370).
 *            - step 3 calls SetActiveSource, which is setActiveSource(false) (cpp:1454-1459).
 *              With isResponse false the "TV is not current Active Source" guard is skipped, so
 *              it broadcasts the television's own address and sets m_currentActiveSource =
 *              m_logicalAddressAllocated (cpp:2060-2068). The television's entry carries the
 *              address the HAL reported - 0.0.0.0 under the emulated component - and a default
 *              m_logicalAddress of 0, so the reading becomes logical address 0 at "0.0.0.0" on
 *              port "TV", the branch GetActiveSource takes when the first nibble is zero.
 *            - step 4 posts ["0x50","0x9D","0x20","0x00"] - a DIRECTED <Inactive Source> from
 *              logical address 5. updateInActiveSource clears that peer's own active-source flag
 *              but leaves m_currentActiveSource alone unless the departing peer IS the current
 *              source (cpp:2121-2128), and after step 3 the current source is the television. So
 *              the correct outcome is NO CHANGE, and that is asserted as an equality against the
 *              step-3 reading rather than as a shape.
 *
 *          This case closes the end-to-end leg of SetActiveSource, which the L2 suite already
 *          covers in-process but which had no device-level counterpart.
 *
 *          It follows TCID17_Request_Active_Source_Flow in the suite's declared order. TCID17
 *          leaves logical address 4 holding the source; step 2 here re-establishes exactly that
 *          state as its own act, so the case neither inherits it nor depends on it and behaves
 *          identically when selected on its own by name.
 *
 *          Only what a JSON-RPC query can observe is asserted. The sink also publishes an
 *          active-source notification, but a curl-driven device-level case cannot subscribe to
 *          one, so nothing here is written as an event assertion.
 *
 *          THE STATE IS PUT BACK by this module's cleanup() hook, which SuitManager runs
 *          unconditionally. It reproduces the three states this suite can express - no active
 *          source, the sink itself, and the announced peer - and reports a residual rather than
 *          inventing a value when the state found at entry was some other peer.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable via the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has seeded the emulated topology, so the peer whose frames are
 *    injected below is already known to the sink.
 *  - The vComponent HTTP API is reachable and the YAML command documents posted below are
 *    readable.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The injected announcement makes logical address 4 the active source at 3.0.0.0 on HDMI2;
 *    setActiveSource then moves it to the television itself, logical address 0 at 0.0.0.0 on
 *    port TV; the directed <Inactive Source> from a non-active peer changes nothing.
 *
 * @pass_criteria
 *  - Both required YAML posts return HTTP 200, setActiveSource acknowledges success: true, the
 *    probe after step 2 reports available True with logicalAddress 4, physicalAddress "3.0.0.0"
 *    and port "HDMI2", the probe after step 3 reports available True with logicalAddress 0,
 *    physicalAddress "0.0.0.0" and port "TV", the probe after step 4 reports the identical
 *    reading to step 3, and run_test() returns True.
 *
 * @failure_criteria
 *  - A rejected vComponent post, a command failure, a JSON parsing error, an unreachable
 *    endpoint, a probe reporting no active source or any field other than the one its step
 *    establishes - a step-3 reading still naming logical address 4 means setActiveSource did
 *    nothing, and a step-4 reading differing from step 3 means the sink cleared a source the
 *    departing peer did not hold; run_test() then returns False.
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


# Only the STATUS CODE is interpreted; the body is logged verbatim as evidence and is never
# parsed. A vComponent that accepts a payload may answer with an empty or non-YAML body, so
# treating the body as structured data would read meaning into text that carries none. The
# code alone is load-bearing: utils.send_vcomponent_command reinterprets no curl exit status,
# so a refused path, an unreadable fixture, a silent server and a server that answered with an
# error all arrive here as a non-200 code rather than as a manufactured success.
def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command."""
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


# THE EXPECTED READINGS, DERIVED FROM THE POSTED DOCUMENTS AND THE HANDLER CHAIN - see @details
# for the derivation of each. They are (logicalAddress, physicalAddress, port) triples so a whole
# reading is compared in one statement and a diagnostic can print both sides side by side.
#
# Step 2 posts commands/Process_Active_Source.yaml: ["0x4F","0x82","0x30","0x00"], broadcast
# <Active Source> from logical address 4 announcing 3.0.0.0.
PEER_ACTIVE_SOURCE = (4, "3.0.0.0", "HDMI2")
# Step 3 calls setActiveSource, which makes the television itself the source. Its address is the
# one the HAL reported, which is 0.0.0.0 for the emulated component's television, and the port
# branch for a zero first nibble is the literal "TV".
TV_ACTIVE_SOURCE = (0, "0.0.0.0", "TV")


def _reading(result):
    """Reduce a getActiveSource result mapping to the triple this case compares.

    Absent members collapse to None, which cannot equal any expected triple - so a reply missing
    a field fails rather than comparing equal to another reply missing the same field. The
    availability flag is asserted separately by the caller, before this triple is believed.
    Args:
        result: The "result" mapping from a getActiveSource reply
    Returns:
        A (logicalAddress, physicalAddress, port) tuple.
    """
    return (
        result.get("logicalAddress"),
        result.get("physicalAddress"),
        result.get("port"),
    )


def _probe_active_source(label):
    """Read getActiveSource and return its result mapping, or None with the reason logged.

    Three probes in this case share it. Both transport guards are applied - the falsy check for
    an undispatched command and the sentinel prefix check that utils.py documents, which a falsy
    check cannot see because the sentinel is a non-empty string - and the body is parsed here so
    a malformed reply is reported against the step that produced it.
    Args:
        label: Human-readable name of the probe, used in the diagnostics
    Returns:
        The "result" mapping when the probe answered with a well-formed success reply,
        otherwise None.
    """
    response = send_curl_command(HdmiCecSinkApis.get_active_source)
    if not response:
        log_error(f"✖ {label} getActiveSource command not sent")
        return None
    if response.startswith("< No response"):
        log_error(f"✖ {label} getActiveSource got no response from WPEFramework")
        return None
    log_warning(f"  {label} active source: {response}")
    try:
        body = json.loads(response)
    except json.JSONDecodeError:
        log_error(f"✖ {label} getActiveSource returned a body that is not JSON")
        return None
    result = body.get("result")
    if not isinstance(result, dict):
        log_error(f"✖ {label} getActiveSource carried no result object")
        return None
    if result.get("success") is not True:
        log_error(f"✖ {label} getActiveSource did not report success")
        log_warning(f"Actual  : {json.dumps(body, indent=2, sort_keys=True)}")
        return None
    return result


# The YAML fixtures cleanup() needs, named here so the restore path and the flow read the same
# documents. Process_In_Active_Source.yaml is the BROADCAST <Inactive Source>; it is the pair used
# by TCID17's restore path to clear a selection, and it is used for the same purpose below.
INACTIVE_SOURCE_YAML = "Process_In_Active_Source.yaml"
ACTIVE_SOURCE_YAML = "Process_Active_Source.yaml"

# The active-source reading observed before this case arranged anything, handed to cleanup().
# None means it was never captured - the probe failed, or run_test() never ran at all - so there
# is nothing to put back and cleanup() says so instead of guessing.
_captured_active_source = None


def run_test():
    start_time = time.perf_counter()

    # ---------- BEFORE-PROBE ----------
    # Recorded rather than asserted. Whichever peer last announced itself holds the active source
    # when this case starts, and the suite pins no particular one, so the starting state is
    # evidence for the transitions below and never a precondition of one. Step 1 below establishes
    # the state every later assertion is measured from, so nothing depends on this reading.
    log_info("Reading the active source before the flow runs")
    before = _probe_active_source("initial")

    if before is None:
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    # CAPTURED BEFORE THE FIRST MUTATION, AND ONLY ONCE IT IS KNOWN TO BE A REAL READING.
    #
    # Everything below this line changes the sink's notion of the active source, so this is the
    # last moment at which the state this case found can still be recorded. It is captured after
    # the None check rather than before it, because a failed probe is not a state - restoring
    # "whatever the probe could not read" would be a second uncontrolled change dressed up as a
    # cleanup. Only the two members cleanup() can act on are kept; the physical address and port
    # are derived from the logical address by the plugin and are not separately settable.
    global _captured_active_source
    _captured_active_source = {
        "available": before.get("available"),
        "logicalAddress": before.get("logicalAddress"),
    }

    before_reading = _reading(before)
    log_info(
        f"  Starting point: available={before.get('available')} reading={before_reading}"
    )

    # ---------- STEP 1: give the source to a peer, and prove it landed ----------
    # This is the state the setter must be seen to change, so it is established FIRST and
    # verified before the setter runs. The frame is BROADCAST because process(ActiveSource)
    # early-returns on directed framing (cpp:155-159) - a directed frame would be accepted by
    # the vComponent and silently discarded by the plugin, leaving a green test that exercised
    # nothing. The peer side arrives only as a frame injected into the already-configured
    # emulated topology; the device under test is never reconfigured to act as its own peer.
    log_info("Injecting the broadcast <Active Source> announcement from the peer")
    if not _post_hdmicec("Process_Active_Source.yaml"):
        log_error("✖ the required <Active Source> injection was rejected")
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    peer_state = _probe_active_source("after the peer announcement")
    if peer_state is None:
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    if peer_state.get("available") is not True:
        log_error(
            "✖ no active source is reported after the broadcast announcement, so the frame "
            "was not processed and there is no state for setActiveSource to change"
        )
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    peer_reading = _reading(peer_state)
    if peer_reading != PEER_ACTIVE_SOURCE:
        log_error(
            f"✖ after the announcement the active source reads {peer_reading}, expected "
            f"{PEER_ACTIVE_SOURCE} as (logicalAddress, physicalAddress, port)"
        )
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    log_success(f"✔ the peer holds the active source: {peer_reading}")

    # ---------- STEP 2: take the source with setActiveSource, and prove it moved ----------
    # setActiveSource takes NO parameters - it asks the sink to become the active source itself.
    # setActivePath, which does carry a parameter, is a different API belonging to the
    # routing-change case; it is deliberately not exercised here.
    log_info("Executing the curl command set active source")
    curl_response = send_curl_command(HdmiCecSinkApis.set_active_source)

    if not curl_response:
        log_error("✖ setActiveSource command not sent")
        return False

    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_success("✔ curl command sent")
    log_warning(f"Response: {curl_response}")

    try:
        set_body = json.loads(curl_response)
    except json.JSONDecodeError:
        log_error("✖ setActiveSource returned a body that is not JSON")
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    # The acknowledgement is asserted as well as the effect. They are different failures: a
    # refused call answers without success, while a call that succeeds and changes nothing is the
    # defect this case exists to catch, and only the probe below can see that one.
    if set_body.get("result", {}).get("success") is not True:
        log_error("✖ setActiveSource did not report success")
        log_warning(f"Actual  : {json.dumps(set_body, indent=2, sort_keys=True)}")
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    time.sleep(CEC_FRAME_PACING_SECONDS)
    tv_state = _probe_active_source("after setActiveSource")
    if tv_state is None:
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    if tv_state.get("available") is not True:
        log_error("✖ no active source is reported after setActiveSource")
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    tv_reading = _reading(tv_state)
    if tv_reading != TV_ACTIVE_SOURCE:
        log_error(
            f"✖ after setActiveSource the active source reads {tv_reading}, expected "
            f"{TV_ACTIVE_SOURCE} as (logicalAddress, physicalAddress, port). Still reading "
            f"{PEER_ACTIVE_SOURCE} would mean the call was acknowledged and did nothing"
        )
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    log_success(f"✔ setActiveSource moved the source to the television: {tv_reading}")

    # ---------- STEP 3: a departing peer that is NOT the source must change nothing ----------
    # Device_In_Active_Source.yaml carries a DIRECTED header (0x50) because the sink's
    # <Inactive Source> handler is directed-only (cpp:165-170); a broadcast frame would be
    # discarded and this step would assert its no-change outcome against a frame that never
    # reached a handler. Device_Request_Inactive_Source.yaml is a historical alias carrying the
    # identical payload; the handler-named fixture is used so the intent reads at the call site.
    #
    # The frame announces logical address 5 standing down. updateInActiveSource clears that
    # peer's own flag and only resets the current source when the departing peer IS the current
    # source (cpp:2121-2128) - which after step 2 is the television. So the correct behaviour is
    # to leave the reading untouched, and that is asserted as equality against step 2's reading
    # rather than against a shape.
    log_info("Injecting the directed <Inactive Source> from a peer that is not the source")
    if not _post_hdmicec("Device_In_Active_Source.yaml"):
        log_error("✖ the required <Inactive Source> injection was rejected")
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    final_state = _probe_active_source("after the inactive-source announcement")
    if final_state is None:
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    final_reading = _reading(final_state)
    if final_state.get("available") is not True or final_reading != tv_reading:
        log_error(
            "✖ the directed <Inactive Source> from a peer that did not hold the source changed "
            f"the reported active source: {tv_reading} (available "
            f"{tv_state.get('available')}) became {final_reading} (available "
            f"{final_state.get('available')})"
        )
        log_error("TCID18_Set_Active_Source_Flow Failed ❌")
        return False

    log_success(
        "✔ the inactive-source announcement from a non-active peer left the active source "
        f"unchanged at {final_reading}"
    )
    log_info(
        f"  Transition observed: {before_reading} -> {peer_reading} -> {tv_reading} -> "
        f"{final_reading}"
    )

    # THE VERDICT LINE GOES THROUGH THE SHARED TIMING HELPER. An earlier revision read
    # os.environ["HDMICEC_TIMING_ENABLED"] here without importing os, so the documented -t mode -
    # the only mode that takes this branch - raised NameError on the last line of a passing case
    # and turned a green run red for a reason that had nothing to do with the device. utils.
    # log_with_timing applies the same policy for every case in the suite and returns text, which
    # is why log_success wraps it rather than being chosen by the caller.
    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID18_Set_Active_Source_Flow Passed ✅", elapsed_time))
    return True


# SHARED STATE THIS CASE CHANGES, AND HOW IT IS PUT BACK
# ------------------------------------------------------
# This block used to be headed "AND WHY IT IS NOT RESTORED" and argued that leaving the television
# holding the active source was acceptable because the next case in the declared order
# re-establishes routing state for itself. Two things were wrong with that. The module's own
# @details section promised a cleanup() hook that reproduces the states this suite can express -
# so the file contradicted itself, and a reader had no way to tell which half was true. And the
# argument only holds while the declared order holds: a case selected on its own, a re-ordered
# registry, or a run that stops after this case all leave the device changed with nothing
# following to absorb it.
#
# The state is therefore captured before the first mutation and restored by cleanup() below, which
# SuitManager runs unconditionally. On a passing run the state this case leaves at the end of
# run_test() is still the television itself - logical address 0 at 0.0.0.0 on port TV, because
# step 2 is the last write and step 3 is asserted to change nothing - and cleanup() is what turns
# that from a residual into a transient.
#
# What cleanup() cannot reproduce is named rather than approximated: this suite's fixtures can
# announce exactly one peer (logical address 4, via ACTIVE_SOURCE_YAML) and can clear the
# selection, and setActiveSource can select the sink itself. An entry state naming any OTHER peer
# is reported as a residual with both readings, because inventing a value would be a second
# uncontrolled change presented as a restoration.


def cleanup():
    '''Put the sink's notion of the active source back where this case found it.

    SuitManager runs this unconditionally - after a pass, a failure, an exception, and even for a
    case it SKIPPED because a producer failed - so it assumes nothing about how far run_test() got
    and is idempotent: the capture is consumed on read, so a second call finds nothing to do.

    Three entry states can be reproduced, and each is confirmed by re-reading the observable
    rather than trusted because a post or a call was accepted:
      * no active source        -> broadcast <Inactive Source>, then confirm availability is gone;
      * the sink itself         -> setActiveSource, then confirm the reading is the television's;
      * the announced peer (LA 4) -> broadcast <Active Source>, then confirm the peer's reading.
    Any other entry state is reported as a residual.

    Returns:
        True when there was nothing to restore, or the captured state was reproduced AND
        confirmed. False when a required post or call was refused, when the restore could not be
        confirmed within the fixture's pacing window, or when the captured state names a peer no
        fixture in this suite can announce.
    '''
    global _captured_active_source
    if _captured_active_source is None:
        log_info("TCID18 cleanup: no active-source state was captured, nothing to restore")
        return True

    captured = _captured_active_source
    _captured_active_source = None

    current = _probe_active_source("cleanup entry")
    if current is not None and (
        current.get("available") == captured.get("available")
        and current.get("logicalAddress") == captured.get("logicalAddress")
    ):
        log_info("TCID18 cleanup: the active source is already as it was found")
        return True

    if captured.get("available") is not True:
        log_info("TCID18 cleanup: restoring 'no active source'")
        if not _post_hdmicec(INACTIVE_SOURCE_YAML):
            log_error("TCID18 cleanup: the required post was refused, active source left as it is")
            return False
        time.sleep(CEC_FRAME_PACING_SECONDS)
        after = _probe_active_source("cleanup after clearing")
        if after is None or after.get("available") is True:
            log_error(
                "TCID18 cleanup: the active source did not clear; last reading "
                f"{None if after is None else _reading(after)}"
            )
            return False
        log_success("✔ TCID18 cleanup: no active source, as found")
        return True

    if captured.get("logicalAddress") == TV_ACTIVE_SOURCE[0]:
        log_info("TCID18 cleanup: re-selecting the television as active source")
        response = send_curl_command(HdmiCecSinkApis.set_active_source)
        if not response or response.startswith("< No response"):
            log_error("TCID18 cleanup: setActiveSource was not answered, state left as it is")
            return False
        time.sleep(CEC_FRAME_PACING_SECONDS)
        after = _probe_active_source("cleanup after re-selecting the television")
        if after is None or _reading(after) != TV_ACTIVE_SOURCE:
            log_error(
                "TCID18 cleanup: the television did not become active source again; last reading "
                f"{None if after is None else _reading(after)}"
            )
            return False
        log_success("✔ TCID18 cleanup: the television holds the active source, as found")
        return True

    if captured.get("logicalAddress") == PEER_ACTIVE_SOURCE[0]:
        log_info(f"TCID18 cleanup: re-announcing LA {PEER_ACTIVE_SOURCE[0]} as active source")
        if not _post_hdmicec(ACTIVE_SOURCE_YAML):
            log_error("TCID18 cleanup: the announcement was refused, state left as it is")
            return False
        time.sleep(CEC_FRAME_PACING_SECONDS)
        after = _probe_active_source("cleanup after re-announcing the peer")
        if after is None or _reading(after) != PEER_ACTIVE_SOURCE:
            log_error(
                "TCID18 cleanup: the peer did not become active source again; last reading "
                f"{None if after is None else _reading(after)}"
            )
            return False
        log_success("✔ TCID18 cleanup: the announced peer holds the active source, as found")
        return True

    log_warning(
        "TCID18 cleanup: the active source found at entry was LA "
        f"{captured.get('logicalAddress')}, which no fixture in this suite can announce, so it "
        "cannot be reproduced. Residual reported rather than approximated: the active source is "
        f"now {None if current is None else _reading(current)}"
    )
    return False
