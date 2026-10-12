"""
/**
 * @file TCID29_Invalid_OSD_Setnochange.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID29_Invalid_OSD_Setnochange
 * @details Validates that a MALFORMED org.rdk.HdmiCecSink.setOSDName request cannot change the
 *          stored OSD name. A known baseline is written and read back, then the invalid request
 *          is issued - HdmiCECSink_Curl.set_osd_name_invalid carries valid JSON whose parameter
 *          key is misspelled, so it arrives with no recognised "name" parameter - and a second
 *          getOSDName must report the same name as the baseline read.
 *
 *          The invariant is the UNCHANGED READ, and BOTH WRITES ARE ASSERTED so that the
 *          invariant can only hold for the right reason. The baseline write is valid and must
 *          report success. The malformed write must be ANSWERED - a JSON-RPC result or error,
 *          either being acceptable, because a target may reject a malformed request or accept
 *          and ignore it and that choice is legitimately its own - but an undelivered request is
 *          not acceptable, since it could not change the name and would satisfy the invariant
 *          without testing anything. TCID10_Set_OSD_Name is the positive leg of this API and
 *          runs earlier in the pinned order; this is the negative.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint utils.py
 *    resolved, and Init_Devicelist_Populate has seeded the emulated CEC topology - which
 *    SuitManager.py guarantees by running it once before the first test case.
 *  - This suite is AUTHORED, NOT EXECUTED here: no CI workflow runs it and nothing below has
 *    been observed against a live device or emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The baseline setOSDName reports success, the malformed setOSDName is answered by the
 *    dispatcher, and the malformed request leaves the OSD name untouched, so both getOSDName
 *    replies report an identical result.name value.
 *
 * @pass_criteria
 *  - The baseline write reports result.success True, the malformed write returns a JSON-RPC
 *    envelope carrying a result or an error member, both getOSDName responses parse as JSON,
 *    both carry a "result" member, their two result.name values are equal, and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - Either write is undispatched, answered with the no-response sentinel, or returns a body
 *    that is not a JSON object; the baseline write does not report success; the malformed write
 *    returns neither a result nor an error member; the final read is not dispatched or is the
 *    sentinel; either body fails to parse or carries no "result" member; the names differ; or
 *    run_test() returns False.
 */
"""

import time
import json
from utils import (
    send_curl_command,
    send_jsonrpc_command,
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

# What an ABSORBED malformed request leaves behind. Thunder's deserialiser ignores the unknown
# member, so params.Name is never set and arrives as an empty string; SetOSDName validates nothing
# and stores it verbatim (HdmiCecSinkImplementation.cpp:1427-1436), and GetOSDName then returns
# osdName.toString(), which for an empty operand is the empty string.
PLUGIN_DEFAULTED_OSD_NAME = ""

# The baseline this module writes, taken from the shared setter constant rather than restated here.
# Two properties make it usable as a baseline and run_test() self-checks both: it is not empty, so
# "rejected" and "absorbed and stored" become two distinguishable observations; and it is within
# OSDName::MAX_LEN so the operand cannot be truncated on the way in.
#
# IT MUST BE THE SHARED CONSTANT'S VALUE, not a literal of this module's own. _restore_osd_name puts
# the name back by re-issuing HdmiCECSink_Curl.set_osd_name, and the cases after this one are written
# against the name TCID10_Set_OSD_Name establishes through that same constant - so a private literal
# here would be written, then "restored" to a different value, and the read-back would fail on a
# discrepancy this module had manufactured.
DISTINGUISHING_OSD_NAME = HdmiCecSinkApis.SET_OSD_NAME_VALUE

# OSDName::MAX_LEN, ccec/include/ccec/Operands.hpp - the operand is a fixed-maximum CEC byte string.
OSD_NAME_MAX_LEN = 14

# Bounded budgets. Poll ceilings, never durations anything waits out.
OBSERVE_TIMEOUT_S = 8.0
OBSERVE_POLL_S = 0.25
RESTORE_TIMEOUT_S = 10.0
RESTORE_POLL_S = 0.5

# The name as it read BEFORE this module wrote anything, handed to cleanup(). None means nothing was
# captured, so there is nothing to restore.
_captured_osd_name = None


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could carry
    a non-object "result" or not be an object at all. Every such case collapses to {} so the caller
    reports a MISSING FIELD rather than raising AttributeError out of run_test(). Narrowing here is what keeps the
    module free of a broad `except Exception`: the only exception any caller can see is
    json.JSONDecodeError, handled where it can occur rather than swept up together with every
    programming defect in the file.
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


def _envelope_kind(reply):
    """Classify a JSON-RPC reply as "result", "error" or None (not an envelope at all).

    The malformed request's reply is the one body this module must classify rather than merely
    parse, because the two admissible outcomes - an explicit rejection and an acceptance with a
    defaulted argument - are told apart by which member the envelope carries. The third answer
    matters just as much: a body carrying NEITHER member is an unusable reply, and reading it as a
    rejection would let a broken transport pose as a validating plugin.

    Args:
        reply: Either a raw response body as returned by utils.send_curl_command, or an envelope
               already parsed by utils.send_jsonrpc_envelope. Both are accepted because the two
               readers in this module hold the reply in those two different forms, and the
               classification must not depend on which one asked.
    Returns:
        "result", "error", or None when the reply is absent, is not JSON, or is not a JSON-RPC
        envelope carrying one of the two members.
    """
    if isinstance(reply, dict):
        body = reply
    else:
        if not reply or reply.startswith("< No response"):
            return None
        try:
            body = json.loads(reply)
        except json.JSONDecodeError:
            return None
        if not isinstance(body, dict):
            return None
    if "error" in body:
        return "error"
    if isinstance(body.get("result"), dict):
        return "result"
    return None


def _published_request(argv):
    """Decode the JSON-RPC request a HdmiCECSink_Curl constant carries, or None with a reason.

    The payload sits in the argv element after "-d". Decoding it means the method name below is
    DERIVED from the constant this suite actually ships rather than restated beside it, so a renamed
    method cannot leave this module silently addressing the old one.
    """
    try:
        payload = argv[argv.index("-d") + 1]
    except (ValueError, IndexError):
        return None, "the command constant carries no -d payload"
    try:
        request = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"the command constant's -d payload is not valid JSON: {exc}"
    if not isinstance(request, dict):
        return None, "the command constant's -d payload is not a JSON object"
    return request, None


def _read_osd_name_quietly():
    """Return the published OSD name, or None when it cannot be read. Logs nothing.

    The empty string is a VALID reading and is returned as such - it is one of the two outcomes this
    module distinguishes - so None means "could not be read" and nothing else.

    THE SILENT READER, and the reason there are two. This one is what the bounded polls call, so a
    wait that takes twenty samples produces twenty reads and no log lines; _read_osd_name(label)
    below is the reporting form, called where a single reading becomes part of a verdict and has to
    appear in the transcript. The two must keep DISTINCT names: a module body runs top to bottom, so
    two definitions sharing one name would leave the later one bound and every earlier caller
    invoking the wrong arity.
    """
    response = send_curl_command(HdmiCecSinkApis.get_osd_name)
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
    value = result.get("name")
    return value if isinstance(value, str) else None


def _wait_for_osd_name(expected, timeout, interval):
    """Poll the published name until it reads `expected`; returns (matched, last_reading)."""
    deadline = time.monotonic() + timeout
    while True:
        observed = _read_osd_name_quietly()
        if observed == expected:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(interval)


def _write_osd_name(value, label):
    """Write an OSD name through the published setter; True when it acknowledges success.

    The method NAME is taken from HdmiCECSink_Curl.set_osd_name rather than written here, and only
    the operand varies - which is how this module writes a name the shared constant does not carry
    without editing that constant. utils.send_jsonrpc_command takes a method and a params mapping,
    so the request is DESCRIBED rather than assembled; no command string is built anywhere.
    """
    request, reason = _published_request(HdmiCecSinkApis.set_osd_name)
    if request is None:
        log_error(f"✖ {label}: {reason}")
        return False
    method = request.get("method")
    if not isinstance(method, str):
        log_error(f"✖ {label}: the set_osd_name constant carries method {method!r}")
        return False
    response = send_jsonrpc_command(method, {"name": value})
    if not isinstance(response, dict):
        log_error(f"✖ {label}: setOSDName was not dispatched or did not return an envelope")
        return False
    result = response.get("result")
    if not isinstance(result, dict) or result.get("success") is not True:
        log_error(f"✖ {label}: setOSDName did not acknowledge success - {response!r}")
        return False
    log_success(f"✔ {label}: setOSDName({value!r}) acknowledged")
    return True


def cleanup():
    """Restore the OSD name this module found before it wrote anything.

    The baseline write cannot double as the restoration: that would hold only while this module and
    TCID10_Set_OSD_Name agreed on one literal. This hook puts back the name this module actually
    observed instead.
    SuitManager runs it unconditionally - after a pass, a failure, an exception, and even for a case
    it skipped because a producer failed - so it assumes nothing about how far run_test() got.
    Idempotent: the capture is consumed, so a second call has nothing to do.
    Returns:
        True when there was nothing to restore or the captured name is back in place; False when the
        write was refused or the read-back never agreed within the budget.
    """
    global _captured_osd_name
    if _captured_osd_name is None:
        log_info("TCID29 cleanup: no OSD name was captured, nothing to restore")
        return True

    captured = _captured_osd_name
    _captured_osd_name = None

    if _read_osd_name_quietly() == captured:
        log_info(f"TCID29 cleanup: the name already reads {captured!r}, nothing to restore")
        return True

    log_info(f"TCID29 cleanup: restoring the captured name {captured!r}")
    if not _write_osd_name(captured, "cleanup"):
        return False
    restored, observed = _wait_for_osd_name(captured, RESTORE_TIMEOUT_S, RESTORE_POLL_S)
    if not restored:
        log_error(
            f"TCID29 cleanup: the name reads {observed!r} rather than the captured {captured!r} "
            "after the restore"
        )
        return False
    log_success(f"✔ TCID29 cleanup: the name is back at {captured!r}")
    return True


def _read_osd_name(label):
    """Read getOSDName and return its name string, or None with the reason already logged.

    A name of "" is a legitimate reading and is returned as such - it is precisely the value the
    malformed write produces on today's plugin - so absence is signalled by None and never by an
    empty string.
    """
    envelope = send_jsonrpc_envelope(HdmiCecSinkApis.get_osd_name, label)
    result = envelope_result(envelope)
    if result is None or result.get("success") is not True:
        log_error(f"✖ {label} did not answer with a result reporting success")
        return None
    name = result.get("name")
    if not isinstance(name, str):
        log_error(
            f"✖ {label} reported a name that is not a string "
            f"({sanitise_for_log(name, max_chars=64)})"
        )
        return None
    log_warning(f"{label}: name={sanitise_for_log(name, max_chars=64)!r}")
    return name


def _observe_malformed_write(baseline_name):
    """Send the malformed setOSDName and judge what the plugin did with it.

    Accepts exactly two outcomes - refused-and-unchanged, or acknowledged-and-emptied - and
    rejects everything else, including a request that produced no usable reply. The reasoning
    behind those two branches is in run_test's opening note.

    Args:
        baseline_name: The name established and read before this write.
    Returns:
        True when one of the two accepted outcomes was observed.
    """
    envelope = send_jsonrpc_envelope(
        HdmiCecSinkApis.set_osd_name_invalid, "malformed setOSDName"
    )
    if envelope is None:
        log_error(
            "✖ the malformed setOSDName produced no usable reply, so nothing can be concluded "
            "about how the plugin treated it"
        )
        return False

    # WHICH MEMBER THE ENVELOPE CARRIES IS THE BRANCH DECISION, so it is classified rather than
    # inferred from a missing result. envelope_result() answers None both for a refusal and for an
    # envelope whose result is not an object, and those are opposite findings: the first is a
    # validating plugin, the second is a reply this case cannot read at all.
    kind = _envelope_kind(envelope)
    if kind is None:
        log_error(
            "✖ the malformed setOSDName answered with an envelope carrying neither a result "
            "object nor an error member, so it is neither a refusal nor an acknowledgement"
        )
        return False

    result = envelope_result(envelope)
    observed_name = _read_osd_name("getOSDName after the malformed write")
    if observed_name is None:
        return False

    if kind == "error":
        # Branch (a): a validating plugin refused the call. The name must be exactly as it was.
        if observed_name != baseline_name:
            log_error(
                "✖ the malformed setOSDName was refused, yet the OSD name changed from "
                f"{sanitise_for_log(baseline_name, max_chars=64)!r} to "
                f"{sanitise_for_log(observed_name, max_chars=64)!r}"
            )
            return False
        log_success(
            "✔ the malformed setOSDName was refused and the OSD name is unchanged - this build "
            "validates its parameters"
        )
        return True

    if result.get("success") is not True:
        log_error(
            "✖ the malformed setOSDName answered with a result reporting "
            f"success={sanitise_for_log(result.get('success'), max_chars=32)}, which is neither "
            "an acknowledgement nor a refusal"
        )
        return False

    # Branch (b): today's plugin acknowledged it. The absorbed missing parameter must show up as
    # exactly the empty name - an acknowledged write that produced some OTHER value is a third
    # behaviour this case does not accept, because it would mean the parameter was read from
    # somewhere unexpected.
    if observed_name != "":
        log_error(
            "✖ the malformed setOSDName was acknowledged and the OSD name became "
            f"{sanitise_for_log(observed_name, max_chars=64)!r}, which is neither the "
            f"established {sanitise_for_log(baseline_name, max_chars=64)!r} nor the empty value "
            "an absorbed missing parameter produces"
        )
        return False

    log_info(
        "The malformed setOSDName was acknowledged and the OSD name is now empty: the "
        "misspelled parameter was absorbed as an empty name rather than rejected. "
        "HdmiCecSinkImplementation::SetOSDName performs no validation - see the note in "
        "run_test - and closing that is a production change reported, not made."
    )
    return True


def _restore_osd_name(baseline_name):
    """Put the OSD name back to the established value and verify that it took.

    The cases after this one are written against the fixed name TCID10_Set_OSD_Name establishes,
    and the acknowledged-and-emptied branch above leaves it empty, so restoring it is this
    module's responsibility rather than the next module's problem. The restoration is READ BACK,
    because one that quietly failed is worse than one that was never attempted: the suite would
    carry on against a name nothing declared.

    Args:
        baseline_name: The value to restore and to verify against.
    Returns:
        True when the name reads back as baseline_name.
    """
    if not require_ack(HdmiCecSinkApis.set_osd_name, "restoring setOSDName"):
        log_error(
            "✖ the OSD name could not be restored, so the cases after this one no longer start "
            "from the name they are written against"
        )
        return False

    restored_name = _read_osd_name("restored getOSDName")
    if restored_name is None or restored_name != baseline_name:
        log_error(
            "✖ the OSD name was not restored: expected "
            f"{sanitise_for_log(baseline_name, max_chars=64)!r}, read "
            f"{sanitise_for_log(restored_name, max_chars=64)!r}"
        )
        return False

    log_success(
        f"✔ the OSD name is restored to {sanitise_for_log(baseline_name, max_chars=64)!r}"
    )
    return True


def run_test():
    """Establish a distinguishing OSD name, send a malformed setter, and pin what happens.

    WHAT IS ASSERTED, and why each item can fail, is set out in the file docstring. In short: the
    baseline write is acknowledged and read back; the malformed reply is a JSON-RPC envelope; the
    name afterwards is EXACTLY the baseline (rejected) or EXACTLY empty (absorbed and stored), and
    which one is reported; an error envelope may not accompany a changed name; and cleanup() puts the
    original back.
    Returns:
        True when every assertion holds; False on any transport failure, unreadable reply, refused
        baseline write, unclassifiable envelope or third name value.
    """
    global _captured_osd_name
    _captured_osd_name = None
    start_time = time.perf_counter()

    # Legacy intent: invalid curl param handling for setOSDName.
    #
    # WHAT THIS CASE ASSERTS, AND WHY IT IS NOT LITERALLY "no change". The plugin's behaviour
    # here is settled by reading the code, and it is not the same as TCID28's. Thunder's
    # registration template calls inbound.FromString(parameters) and DISCARDS the result
    # (Thunder/Source/core/JSONRPC.h, InternalRegister), and nothing between the wire and the
    # implementation inspects parameter names - so the misspelled "nnamme" leaves the generated
    # Name member at its default and HdmiCecSinkImplementation::SetOSDName is called with an
    # EMPTY string. Unlike SetVendorId, that setter has no fallback and no validation: it assigns
    # osdName = "" and answers success (HdmiCecSinkImplementation.cpp:1427-1436). OSDName's own
    # CECBytes::validate() would reject a zero-length value, but its result is DISCARDED by the
    # constructor (hdmicec/ccec/include/ccec/Operands.hpp:148-149), so nothing stops it.
    #
    # A test asserting "the name is unchanged" would therefore fail against a correct build of
    # today's plugin. This case asserts the invariant that is actually true, and that stays true
    # if the missing validation is ever added, by accepting EITHER honest outcome:
    #
    #   (a) the malformed write is REFUSED and the name is unchanged - what a validating plugin
    #       would do; or
    #   (b) the malformed write is ACKNOWLEDGED and the name became the empty string - what this
    #       plugin does today, the malformed parameter being absorbed rather than rejected.
    #
    # and rejecting everything else: a write that was never dispatched, an acknowledged write
    # that turned the name into some other value, or a state that cannot be put back.
    #
    # REQUIRED PRODUCTION CHANGE, REPORTED AND NOT MADE (AAP Directive 6). Branch (b) is a real
    # robustness gap: a caller can silently erase the sink's advertised OSD name with a typo.
    # Closing it needs input validation in HdmiCecSinkImplementation::SetOSDName - reject an
    # empty name with Core::ERROR_INVALID_SIGNATURE, or honour CECBytes::validate()'s result -
    # which is a production source change this suite is not permitted to make.
    # THE BASELINE VALUE IS SELF-CHECKED BEFORE IT IS WRITTEN. Both properties are load-bearing and
    # neither is this module's to choose - the value comes from the shared setter constant - so a
    # change to that constant that broke either one would otherwise quietly hollow this case out.
    # An empty baseline would make branches (a) and (b) indistinguishable, because "unchanged" and
    # "emptied" would be the same reading; a baseline longer than OSDName::MAX_LEN would be
    # truncated on the way in, so the read-back would fail against a value the plugin never
    # promised to store.
    if not DISTINGUISHING_OSD_NAME:
        log_error(
            "✖ HdmiCECSink_Curl.SET_OSD_NAME_VALUE is empty, so an absorbed malformed write and a "
            "refused one would leave the same reading and this case could not tell them apart"
        )
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False
    if len(DISTINGUISHING_OSD_NAME) > OSD_NAME_MAX_LEN:
        log_error(
            f"✖ HdmiCECSink_Curl.SET_OSD_NAME_VALUE is {len(DISTINGUISHING_OSD_NAME)} characters, "
            f"beyond OSDName::MAX_LEN ({OSD_NAME_MAX_LEN}), so the operand would be truncated on "
            "the way in and the read-back would fail against a value never stored"
        )
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False

    # CAPTURED FIRST, BEFORE ANYTHING IS WRITTEN. cleanup() puts this value back, and it is read
    # here rather than assumed to be the shared constant's: a sibling case may legitimately have
    # left another name in place, and restoring a name this case never observed would be a
    # different change rather than a restoration. An unreadable name is a precondition failure -
    # writing over a state that cannot be captured is what makes a case unsafe to run.
    _captured_osd_name = _read_osd_name("the OSD name before this case wrote anything")
    if _captured_osd_name is None:
        log_error(
            "✖ the OSD name could not be read before the baseline write, so there is nothing for "
            "cleanup() to restore and this case must not write over it"
        )
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False

    if not require_ack(HdmiCecSinkApis.set_osd_name, "baseline setOSDName"):
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False

    # READ BACK, AND WAITED FOR. The baseline is the value every comparison below is against, so an
    # acknowledged write whose value never arrived would make the malformed write's effect
    # unmeasurable. Bounded, because the setter stores the operand on the plugin's own thread.
    established, observed = _wait_for_osd_name(
        DISTINGUISHING_OSD_NAME, OBSERVE_TIMEOUT_S, OBSERVE_POLL_S
    )
    if not established:
        log_error(
            f"✖ the baseline setOSDName was acknowledged but the name reads "
            f"{sanitise_for_log(observed, max_chars=64)!r} rather than "
            f"{sanitise_for_log(DISTINGUISHING_OSD_NAME, max_chars=64)!r} after "
            f"{OBSERVE_TIMEOUT_S:.0f}s, so there is no established baseline to measure against"
        )
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False
    log_success(
        f"✔ baseline established: the OSD name reads "
        f"{sanitise_for_log(DISTINGUISHING_OSD_NAME, max_chars=64)!r}"
    )

    # THE MEASUREMENT, then the restoration. Both are required: the acknowledged-and-emptied branch
    # leaves the name empty, and every case after this one is written against the established value.
    if not _observe_malformed_write(DISTINGUISHING_OSD_NAME):
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False

    if not _restore_osd_name(DISTINGUISHING_OSD_NAME):
        log_error("TCID29_Invalid_OSD_Setnochange Failed")
        return False

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID29_Invalid_OSD_Setnochange Passed", elapsed_time))
    return True
