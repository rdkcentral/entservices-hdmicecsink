"""
/**
 * @file TCID30_Repeated_Disable_Idempotent.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID30_Repeated_Disable_Idempotent
 * @details Validates that org.rdk.HdmiCecSink.setEnabled is idempotent in the disable
 *          direction: two consecutive setEnabled(false) requests must leave getEnabled
 *          reporting false rather than oscillating back to true. Both reads are logged;
 *          only the second is asserted. The module then restores the suite invariant
 *          itself - its last request is setEnabled(true), sent before any guard can
 *          return, so no failure path leaves HDMI-CEC disabled downstream.
 *          TCID31_Repeated_Enable_Idempotent runs next and re-verifies the enabled state.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has run, so HDMI-CEC starts enabled.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - Both disable requests are acknowledged, the reported state is false after EACH of them,
 *    and HDMI-CEC is restored to enabled and verified before the module returns.
 *
 * @pass_criteria
 *  - Each of the three writes - two disables and the restoring enable - is acknowledged with
 *    result.success == true; getEnabled reports a boolean result.enabled of False after both
 *    disables and True after the restoration; and run_test() returns True.
 *
 * @failure_criteria
 *  - Any request is not dispatched, answers with the no-response sentinel, is not a JSON-RPC 2.0
 *    envelope, answers a different request id, does not report success, or reports a
 *    result.enabled that is not a bool; either reading after a disable is not False; the
 *    restoration is refused or does not read back as True; or run_test() returns False.
 *
 *    Reading after BOTH disables is what makes this an idempotence check rather than a single
 *    state check: one reading cannot tell "still false" from "false for the first time".
 *    Verifying the restoration is what keeps a silent failure here from surfacing as a failure
 *    in TCID31_Repeated_Enable_Idempotent, which runs next and needs the plugin enabled.
 */
"""

import time
from utils import (
    send_jsonrpc_envelope,
    envelope_result,
    require_ack,
    sanitise_for_log,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def _read_enabled(label):
    """Read getEnabled and return its boolean state, or None with the reason already logged.

    `enabled` must be a real bool. A missing member, a null, or a truthy 1 or "true" is reported
    as unreadable rather than coerced, because this case's whole subject is a boolean state
    holding still - a coerced value would let an off-contract reply stand in for the reading.
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


def _restore_enabled():
    """Re-enable HDMI-CEC and VERIFY it, since every following case needs it enabled.

    A restoring call whose reply is discarded cannot tell a restoration that failed from one that
    worked, and a silently failed one would leave a disabled plugin to the rest of the suite - the
    very next case, TCID31_Repeated_Enable_Idempotent, would then fail for this module's omission.
    The acknowledgement and the read-back are both required here so the fault is reported where it
    happens.
    """
    if not require_ack(HdmiCecSinkApis.set_enabled_true, "restoring setEnabled(true)"):
        log_error(
            "✖ HDMI-CEC could not be re-enabled, so this case would leave the plugin disabled "
            "for every case that follows it"
        )
        return False

    restored = _read_enabled("restored getEnabled")
    if restored is not True:
        log_error(
            f"✖ HDMI-CEC did not read back as enabled after restoration (enabled={restored}), "
            "so the suite invariant every following case depends on is not in place"
        )
        return False

    log_success("✔ HDMI-CEC is restored to enabled")
    return True


def run_test():
    start_time = time.perf_counter()

    # Legacy intent: getEnabled when already disabled.
    #
    # IDEMPOTENCE NEEDS BOTH READINGS, AND EVERY WRITE ACKNOWLEDGED. The claim is that a second
    # setEnabled(false) against an already-disabled plugin changes nothing, so the state has to
    # be observed after EACH of the two writes - one reading cannot distinguish "still false" from
    # "false for the first time". And a write whose reply is discarded is indistinguishable from
    # one that never left the host: a plugin that was already disabled would report false on both
    # reads whether or not either request arrived, so without the acknowledgements this case could
    # pass on no evidence at all.
    observation_ok = False
    if require_ack(HdmiCecSinkApis.set_enabled_false, "first setEnabled(false)"):
        first_enabled = _read_enabled("getEnabled after the first disable")
        if first_enabled is not None:
            if first_enabled is not False:
                log_error(
                    f"✖ the first setEnabled(false) was acknowledged but getEnabled reports "
                    f"enabled={first_enabled}"
                )
            elif require_ack(HdmiCecSinkApis.set_enabled_false, "repeated setEnabled(false)"):
                second_enabled = _read_enabled("getEnabled after the repeated disable")
                if second_enabled is False:
                    log_success(
                        "✔ a repeated setEnabled(false) is idempotent: enabled read false after "
                        "both acknowledged writes"
                    )
                    observation_ok = True
                elif second_enabled is not None:
                    log_error(
                        "✖ the repeated setEnabled(false) changed the state: enabled="
                        f"{second_enabled}"
                    )

    # RESTORATION RUNS WHATEVER THE OBSERVATION CONCLUDED, and its own result is checked. It is
    # not in a finally block because a return from finally would replace the observation's
    # verdict; the two are combined explicitly below so a failure in either is visible.
    restore_ok = _restore_enabled()

    if not observation_ok or not restore_ok:
        log_error("TCID30_Repeated_Disable_Idempotent Failed")
        return False

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID30_Repeated_Disable_Idempotent Passed", elapsed_time))
    return True
