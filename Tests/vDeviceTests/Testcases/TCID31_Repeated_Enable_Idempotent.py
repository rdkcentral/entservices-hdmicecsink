"""
/**
 * @file TCID31_Repeated_Enable_Idempotent.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID31_Repeated_Enable_Idempotent
 * @details Validates that org.rdk.HdmiCecSink.setEnabled is idempotent in the enable
 *          direction: two consecutive setEnabled(true) requests must leave getEnabled
 *          reporting true rather than oscillating back to false. Both writes are required
 *          to acknowledge and both reads are asserted, the second of them across three
 *          consecutive readings so that "held" is distinguishable from "was right once".
 *          This is the enable-side twin of TCID30_Repeated_Disable_Idempotent, which
 *          disables at the preceding position.
 *
 *          THE DISABLED STATE IS MANUFACTURED FIRST, and that is what gives the case its
 *          subject. TCID30 restores the enabled invariant, so a plugin arriving here is
 *          already enabled and both enables would be no-ops against a state nothing had
 *          moved - satisfied even by a plugin that had stopped honouring setEnabled. One
 *          setEnabled(false), read back, makes the first enable a real transition and the
 *          second the idempotence claim. The disable is transient: the enabled state this
 *          module leaves behind IS the suite invariant - established by
 *          Init_Devicelist_Populate, asserted by TCID01_Get_Enabled_Status - so no
 *          restoration follows the flow, while cleanup() closes the window between the
 *          disable and the re-enable on any path that leaves it open.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has run, so HDMI-CEC starts enabled.
 *  - TCID30_Repeated_Disable_Idempotent has run at the preceding position.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The precondition disable is acknowledged and reads back false; both enable requests
 *    are acknowledged; the reported state is true after each of them and holds true across
 *    three consecutive readings; and HDMI-CEC is left enabled for the remaining test cases.
 *
 * @pass_criteria
 *  - setEnabled(false) is acknowledged and getEnabled reads false within the settle budget,
 *    both setEnabled(true) requests are acknowledged, getEnabled reports a boolean
 *    result.enabled of True after each, three consecutive readings agree, and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - Any request is not dispatched or not acknowledged, a response is the no-response
 *    sentinel, a body does not parse, result.enabled is absent or not a boolean, the
 *    precondition disable never reads back false, either enable does not read back true,
 *    the three confirming readings disagree, or run_test() returns False.
 */
"""

import time
import json
from utils import (
    send_curl_command,
    send_jsonrpc_envelope,
    envelope_result,
    require_ack,
    sanitise_for_log,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
)
import HdmiCECSink_Curl as HdmiCecSinkApis

# Bounded budgets. setEnabled is not a simple assignment - CECEnable() starts the poll thread and
# CECDisable() waits for ARC to reach the terminated state and then joins that thread
# (HdmiCecSinkImplementation.cpp:3060-3140) - so the published flag is read through a bounded poll
# rather than immediately after the call. Poll ceilings, never durations anything waits out.
SETTLE_TIMEOUT_S = 15.0
SETTLE_POLL_S = 0.25

# How many consecutive agreeing readings establish that a value HELD rather than merely happened to
# be observed once. Used for the idempotent repeat, where "still false" is the whole claim.
CONFIRM_READINGS = 3

# True once this module has driven CEC away from the enabled state, so cleanup() can tell "already
# restored" from "must restore".
_enabled_disturbed = False


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could carry
    a non-object "result" or not be an object at all. Every such case collapses to {} so the caller
    reports a MISSING FIELD rather than raising AttributeError out of run_test(). Narrowing here is what keeps the
    module free of a broad exception handler: the only exception a caller can see is
    json.JSONDecodeError, handled where it can occur rather than swept up together with every
    programming defect in the file.
    """
    body = json.loads(response_text)
    if not isinstance(body, dict):
        return {}
    result = body.get("result")
    return result if isinstance(result, dict) else {}


def _read_enabled_quietly():
    """Return the published HDMI-CEC enabled flag, or None when it cannot be read. Logs nothing.

    THE SILENT READER, and the reason there are two. This one is what the bounded polls and the
    repeated-reading confirmation call, so a wait that takes sixty samples produces sixty reads and
    no log lines; _read_enabled(label) below is the reporting form, called where a single reading
    becomes part of a verdict and has to appear in the transcript. The two must keep DISTINCT names:
    a module body runs top to bottom, so two definitions sharing one name would leave the later one
    bound and every earlier caller invoking the wrong arity.
    """
    response = send_curl_command(HdmiCecSinkApis.get_enabled)
    # utils.send_curl_command reports a transport failure by RETURNING the TRUTHY sentinel
    # "< No response from WPEFramework >", so the prefix form is the detection contract.
    if not response or response.startswith("< No response"):
        return None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return None
    if result.get("success") is not True:
        return None
    value = result.get("enabled")
    return value if isinstance(value, bool) else None


def _set_enabled(argv, label):
    """Dispatch one setEnabled request and REQUIRE its acknowledgement.

    Discarding a setter reply makes a request that was never dispatched, one answered with an error
    envelope and one answered with success false indistinguishable from one that worked, which would
    leave the verdict resting on a single read that pre-existing state could satisfy.
    HdmiCecSinkImplementation::SetEnabled sets success unconditionally, so requiring True proves the
    call REACHED the plugin rather than proving the transition; the transition is proven by the
    read-back that follows.
    """
    response = send_curl_command(argv)
    if not response:
        log_error(f"✖ {label}: setEnabled command not sent")
        return False
    if response.startswith("< No response"):
        log_error(f"✖ {label}: setEnabled returned no response from WPEFramework")
        return False
    log_info(f"  {label}: {response}")
    try:
        if _result_object(response).get("success") is not True:
            log_error(f"✖ {label}: setEnabled did not acknowledge success")
            return False
    except json.JSONDecodeError:
        log_error(f"✖ {label}: setEnabled reply is not valid JSON")
        return False
    log_success(f"✔ {label}: setEnabled acknowledged")
    return True


def _wait_for_enabled(expected):
    """Poll the published flag until it reads `expected`; returns (matched, last_reading)."""
    deadline = time.monotonic() + SETTLE_TIMEOUT_S
    while True:
        observed = _read_enabled_quietly()
        if observed is expected:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(SETTLE_POLL_S)


def _confirm_held(expected):
    """Require CONFIRM_READINGS consecutive readings of `expected`; returns (held, last_reading).

    One reading cannot distinguish "the value held" from "the value happened to be right at the
    moment it was sampled", and the idempotent repeat's entire claim is that the value HELD.
    """
    for _ in range(CONFIRM_READINGS):
        observed = _read_enabled_quietly()
        if observed is not expected:
            return False, observed
        time.sleep(SETTLE_POLL_S)
    return True, expected


def cleanup():
    """Guarantee HDMI-CEC is left ENABLED - the suite invariant this module deliberately disturbs.

    THIS IS WHY THE HOOK EXISTS AS WELL AS THE finally CLAUSE. SuitManager runs cleanup() for every
    registered case unconditionally - after a pass, a failure, an exception, and even for a case it
    SKIPPED because its producer failed - so a run in which run_test() never executed at all still
    leaves CEC enabled. A finally clause inside run_test() cannot cover that path.
    Idempotent: when run_test() has already restored the flag, this reports that and does nothing.
    Returns:
        True when there was nothing to restore or CEC is enabled again; False when the request was
        refused or the flag never came back within its budget.
    """
    global _enabled_disturbed
    if not _enabled_disturbed:
        log_info("TCID31 cleanup: HDMI-CEC was not left disturbed, nothing to restore")
        return True
    _enabled_disturbed = False

    log_info("TCID31 cleanup: re-enabling HDMI-CEC so the suite invariant holds")
    if not _set_enabled(HdmiCecSinkApis.set_enabled_true, "cleanup re-enable"):
        log_error("TCID31 cleanup: HDMI-CEC could not be re-enabled and may be left disabled")
        return False
    restored, observed = _wait_for_enabled(True)
    if not restored:
        log_error(
            f"TCID31 cleanup: HDMI-CEC reads {observed!r} rather than True after the re-enable"
        )
        return False
    log_success("✔ TCID31 cleanup: HDMI-CEC is enabled again")
    return True


def _read_enabled(label):
    """Read getEnabled and return its boolean state, or None with the reason already logged.

    `enabled` must be a real bool: a missing member, a null, or a truthy 1 or "true" is reported
    as unreadable rather than coerced. This case's subject is a boolean state holding still, and a
    coerced value would let an off-contract reply stand in for the reading.
    """
    envelope = send_jsonrpc_envelope(HdmiCecSinkApis.get_enabled, label)
    result = envelope_result(envelope)
    if result is None or result.get("success") is not True:
        log_error(f"✖ {label} did not answer with a result reporting success")
        return None
    enabled = result.get("enabled")
    if not isinstance(enabled, bool):
        log_error(
            f"✖ {label} did not report a boolean enabled member "
            f"({sanitise_for_log(enabled, max_chars=32)})"
        )
        return None
    log_warning(f"{label}: enabled={enabled}")
    return enabled


def run_test():
    """Manufacture the disabled state, enable twice, and require the flag to hold enabled.

    Returns:
        True when every setEnabled acknowledges and every read-back agrees; False on any transport
        failure, unacknowledged request, unreadable flag or transition that never happened. HDMI-CEC
        is enabled on every exit path - by this function on the paths that reach its end, and by
        cleanup() on the paths that return early with the state still disturbed.
    """
    global _enabled_disturbed
    _enabled_disturbed = False
    start_time = time.perf_counter()

    # Legacy intent: getEnabled when already enabled.
    #
    # IDEMPOTENCE NEEDS BOTH READINGS, AND EVERY WRITE ACKNOWLEDGED - the same reasoning as
    # TCID30_Repeated_Disable_Idempotent, and it bites harder here. Enabled is the suite's
    # standing invariant, so the plugin arrives at this case already enabled: a reading of true
    # proves nothing at all unless the write that preceded it was acknowledged. With the replies
    # discarded, this case would have reported a pass with neither request reaching the device.
    #
    # AND THE DISABLED STATE IS MANUFACTURED FIRST, which is what makes the first enable a real
    # TRANSITION rather than a second no-op. TCID30_Repeated_Disable_Idempotent runs immediately
    # before this case and restores the enabled invariant, so without this step the plugin arrives
    # already enabled and BOTH enables would be no-ops - the case would then be asserting only that
    # an already-true flag stayed true, which a plugin that had stopped honouring setEnabled
    # entirely would satisfy. The disable is transient and this module's terminal state is still
    # enabled, so the suite invariant the file docstring describes is unaffected; _enabled_disturbed
    # is what lets cleanup() close the window between the disable and the re-enable if anything
    # raises inside it.
    if not _set_enabled(HdmiCecSinkApis.set_enabled_false, "precondition setEnabled(false)"):
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False
    _enabled_disturbed = True

    disabled, observed = _wait_for_enabled(False)
    if not disabled:
        log_error(
            f"✖ the precondition setEnabled(false) was acknowledged but getEnabled reports "
            f"enabled={observed!r} after {SETTLE_TIMEOUT_S:.0f}s, so the enables that follow would "
            "not be transitions and their idempotence would be untested"
        )
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False
    log_success("✔ precondition established: HDMI-CEC reads disabled")

    if not require_ack(HdmiCecSinkApis.set_enabled_true, "first setEnabled(true)"):
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False

    # Waited for before it is reported: CECEnable() starts the poll thread rather than assigning a
    # flag, so an immediate read can legitimately still be false.
    enabled, observed = _wait_for_enabled(True)
    if not enabled:
        log_error(
            f"✖ the first setEnabled(true) was acknowledged but getEnabled reports "
            f"enabled={observed!r} after {SETTLE_TIMEOUT_S:.0f}s"
        )
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False

    first_enabled = _read_enabled("getEnabled after the first enable")
    if first_enabled is not True:
        log_error(
            "✖ the first setEnabled(true) was acknowledged but getEnabled reports enabled="
            f"{first_enabled}"
        )
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False

    if not require_ack(HdmiCecSinkApis.set_enabled_true, "repeated setEnabled(true)"):
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False

    second_enabled = _read_enabled("getEnabled after the repeated enable")
    if second_enabled is not True:
        log_error(
            f"✖ the repeated setEnabled(true) changed the state: enabled={second_enabled}"
        )
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False

    # HELD, NOT MERELY OBSERVED. The repeat's whole claim is that the state did not move, and a
    # single sample cannot tell "it held" from "it was right at the instant it was read" - the
    # repeated enable runs CECEnable()'s guard path, and a plugin that briefly tore the connection
    # down and rebuilt it would satisfy one reading and fail three.
    held, observed = _confirm_held(True)
    if not held:
        log_error(
            f"✖ HDMI-CEC did not hold enabled across {CONFIRM_READINGS} consecutive readings "
            f"after the repeated enable: read {observed!r}"
        )
        log_error("TCID31_Repeated_Enable_Idempotent Failed")
        return False
    log_success(
        f"✔ a repeated setEnabled(true) is idempotent: enabled read true after both acknowledged "
        f"writes and held across {CONFIRM_READINGS} consecutive readings"
    )

    # No restoration request follows, deliberately: enabled IS the suite invariant, so this
    # module's terminal state is already the wanted one. That is the intentional asymmetry
    # with TCID30_Repeated_Disable_Idempotent, which must send a trailing set_enabled_true.
    # The flag is cleared here rather than left set, so cleanup() reports "nothing to restore"
    # instead of re-issuing an enable the case has just proven is in force - and so that an early
    # return from any of the guards ABOVE this point, where the state genuinely is disturbed,
    # still leaves cleanup() with the restoration to do.
    _enabled_disturbed = False

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID31_Repeated_Enable_Idempotent Passed", elapsed_time))
    return True
