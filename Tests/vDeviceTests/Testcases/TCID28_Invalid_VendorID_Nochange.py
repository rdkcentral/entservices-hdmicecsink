"""
/**
 * @file TCID28_Invalid_VendorID_Nochange.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID28_Invalid_VendorID_Nochange
 * @details Validates what a malformed org.rdk.HdmiCecSink.setVendorId request may do to the
 *          advertised vendor identifier: a DISTINGUISHING identifier is written through the
 *          published setter and read back exactly, the request whose parameter key is
 *          misspelled is sent, and the identifier is read again. Afterwards it must be
 *          EXACTLY ONE OF two values, and which one is reported - the distinguishing
 *          baseline, meaning the request was refused or ignored, or the plugin's documented
 *          0x0019FB fallback, meaning the misspelt member was absorbed as an empty
 *          identifier and SetVendorId's catch-all substituted its literal. A third value
 *          fails. The malformed reply is CLASSIFIED rather than required to acknowledge,
 *          because both a refusal and an acknowledgement are legitimate answers; a body that
 *          is neither fails, since that is a transport failure and not a plugin choice. An
 *          error envelope paired with a changed identifier fails too - a refused request
 *          cannot have applied anything.
 *
 *          WHY THE BASELINE IS NOT THE SHARED CONSTANT'S VALUE. HdmiCECSink_Curl.set_vendor_id
 *          writes 0x0019FB, which is also the fallback, so baselining with it made "refused"
 *          and "absorbed and defaulted" the same reading and the case could not fail. The
 *          misspelled key lives in HdmiCECSink_Curl.set_vendor_id_invalid and only there.
 *          This is the negative leg of a triple - TCID11_Set_Vendor_ID is the positive write,
 *          TCID12_Verify_Vendor_ID_Readback the readback - and because it now writes a value
 *          of its own it creates a residual, which cleanup() restores to whatever the
 *          identifier read before this case wrote anything.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has run, so the CEC topology is seeded.
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
 *  - The distinguishing baseline is acknowledged and reads back exactly; the malformed
 *    request answers with a JSON-RPC result or error envelope; the identifier afterwards is
 *    either that baseline or the plugin's 0x0019FB fallback, and which one is reported; and
 *    cleanup() restores the identifier this case found before it wrote anything.
 *
 * @pass_criteria
 *  - The distinguishing baseline renders differently from the fallback, the pre-case
 *    identifier is readable and captured, the baseline write is acknowledged and reads back
 *    within the observe budget, the malformed reply classifies as a result or an error
 *    envelope, the final read carries a non-empty vendorid string, that value is either the
 *    baseline or the fallback, an error envelope is not paired with a changed identifier, and
 *    run_test() returns True.
 *
 * @failure_criteria
 *  - The baseline and the fallback render alike, the pre-case identifier cannot be read, the
 *    baseline write is refused or never reads back, the malformed reply is neither a result
 *    nor an error envelope, the final read is empty or lacks a usable vendorid, the final
 *    value is neither the baseline nor the fallback, an error envelope accompanies a changed
 *    identifier, a parse error occurs, or run_test() returns False.
 */
"""

import time
import json
from utils import (
    send_curl_command,
    send_jsonrpc_command,
    send_jsonrpc_envelope,
    envelope_result,
    sanitise_for_log,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
)
import HdmiCECSink_Curl as HdmiCecSinkApis

# THE LITERAL HdmiCecSinkImplementation::SetVendorId FALLS BACK TO when the identifier it is
# handed cannot be parsed. The routine wraps stoi(vendorId, NULL, 16) in a catch-all and, on an
# exception, substitutes 0x0019FB before persisting it (HdmiCecSinkImplementation.cpp:1568-1613).
# That literal is the reason this module exists in its present form: it is ALSO the value
# HdmiCECSink_Curl.set_vendor_id writes, so a case that baselines with the positive constant and
# then asserts "unchanged" cannot fail - the malformed request's own default lands on the value
# being compared against.
PLUGIN_FALLBACK_VENDOR_ID = 0x0019FB

# The baseline this module writes instead, chosen for ONE property: it must render differently
# from the fallback above, so that "rejected" and "absorbed and defaulted" become two
# distinguishable observations rather than one indistinguishable pass.
DISTINGUISHING_VENDOR_ID = 0x00AABB

# Bounded budget for the read-backs. A poll ceiling, never a duration anything waits out.
OBSERVE_TIMEOUT_S = 8.0
OBSERVE_POLL_S = 0.25
RESTORE_TIMEOUT_S = 10.0
RESTORE_POLL_S = 0.5

# The identifier as it read BEFORE this module wrote anything, handed to cleanup(). None means
# nothing was captured, so there is nothing to restore.
_captured_vendor_id = None


def _render_vendor_id(value):
    """Render a 24-bit vendor identifier the way the plugin publishes it.

    NOT A GUESS, AND NOT A LITERAL COPIED FROM A LOG. SetVendorId splits the parsed integer into
    three bytes - (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff - and GetVendorId returns
    appVendorId.toString(), which is CECBytes::toString(): a stringstream that streams each byte
    with std::hex and NO width, NO fill and NO separator (ccec/include/ccec/Operands.hpp:48-54).
    So 0x0019FB is published as "019fb", not "0x0019FB" and not "0019fb". Reproducing that
    arithmetic here is what lets this module compare identities instead of hoping a literal
    matches.
    Args:
        value: The 24-bit identifier as an integer.
    Returns:
        The string GetVendorId is expected to return for it.
    """
    return "".join(f"{(value >> shift) & 0xFF:x}" for shift in (16, 8, 0))


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could
    carry a non-object "result" or not be an object at all. Every such case collapses to {} so the
    caller reports a MISSING FIELD rather than raising AttributeError out of run_test(). Narrowing
    here is what keeps the module free of a broad `except Exception`: the only exception any caller
    can see is json.JSONDecodeError, which is handled where it can occur rather than swept up with
    every programming defect in the file.
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


def _envelope_kind(response_text):
    """Classify a JSON-RPC reply as "result", "error" or None (not an envelope at all).

    The malformed request's reply is the one body this module must classify rather than merely
    parse, because the two admissible outcomes - an explicit rejection and an acceptance with a
    defaulted argument - are told apart by which member the envelope carries.
    Returns:
        "result", "error", or None when the body is not JSON or is not a JSON-RPC envelope.
    """
    if not response_text or response_text.startswith("< No response"):
        return None
    try:
        body = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    if "error" in body:
        return "error"
    if isinstance(body.get("result"), dict):
        return "result"
    return None


def _read_vendor_id():
    """Return the published vendor identifier, or None when it cannot be read."""
    response = send_curl_command(HdmiCecSinkApis.get_vendor_id)
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
    value = result.get("vendorid")
    return value if isinstance(value, str) else None


def _wait_for_vendor_id(expected, timeout, interval):
    """Poll the published identifier until it reads `expected`; returns (matched, last_reading)."""
    deadline = time.monotonic() + timeout
    while True:
        observed = _read_vendor_id()
        if observed == expected:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(interval)


def _write_vendor_id(value, label):
    """Write a vendor identifier through the published setter; True when it acknowledges success.

    The method NAME is taken from HdmiCECSink_Curl.set_vendor_id rather than written here, and only
    the operand varies - which is how this module writes a value the shared constant does not carry
    without editing that constant. utils.send_jsonrpc_command takes a method and a params mapping,
    so the request is DESCRIBED rather than assembled; no command string is built anywhere.
    """
    request, reason = _published_request(HdmiCecSinkApis.set_vendor_id)
    if request is None:
        log_error(f"✖ {label}: {reason}")
        return False
    method = request.get("method")
    if not isinstance(method, str):
        log_error(f"✖ {label}: the set_vendor_id constant carries method {method!r}")
        return False
    response = send_jsonrpc_command(method, {"vendorid": f"0x{value:06X}"})
    if not isinstance(response, dict):
        log_error(f"✖ {label}: setVendorId was not dispatched or did not return an envelope")
        return False
    result = response.get("result")
    if not isinstance(result, dict) or result.get("success") is not True:
        log_error(f"✖ {label}: setVendorId did not acknowledge success - {response!r}")
        return False
    log_success(f"✔ {label}: setVendorId(0x{value:06X}) acknowledged")
    return True


def _published_request(argv):
    """Decode the JSON-RPC request a HdmiCECSink_Curl constant carries, or None with a reason.

    The payload sits in the argv element after "-d". Decoding it means the method name below is
    DERIVED from the constant this suite actually ships rather than restated beside it, so a
    renamed method cannot leave this module silently addressing the old one.
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


def cleanup():
    """Restore the vendor identifier this module found before it wrote anything.

    This module deliberately writes a DISTINGUISHING value so its negative step can be falsified,
    which creates a residual - and a residual a module creates, it restores.
    SuitManager runs this unconditionally - after a pass, a failure, an exception, and even for a
    case it skipped because a producer failed - so it assumes nothing about how far run_test() got.
    Idempotent: the capture is consumed, so a second call has nothing to do.
    Returns:
        True when there was nothing to restore or the captured identifier is back in place; False
        when the write was refused or the read-back never agreed within the budget.
    """
    global _captured_vendor_id
    if _captured_vendor_id is None:
        log_info("TCID28 cleanup: no vendor identifier was captured, nothing to restore")
        return True

    captured = _captured_vendor_id
    _captured_vendor_id = None

    if _read_vendor_id() == captured:
        log_info(f"TCID28 cleanup: the identifier already reads {captured!r}, nothing to restore")
        return True

    # The captured reading is a RENDERED identity, not the integer that produced it, and the setter
    # takes the integer - so the integer is recovered from the rendering. CECBytes::toString()
    # emits each byte with std::hex and no padding, so the rendering is not reversible in general;
    # the two identities this module can have left behind are known, and anything else is reported
    # rather than guessed at.
    for candidate in (DISTINGUISHING_VENDOR_ID, PLUGIN_FALLBACK_VENDOR_ID):
        if _render_vendor_id(candidate) == captured:
            break
    else:
        log_error(
            f"TCID28 cleanup: the captured identifier {captured!r} is neither of the two values "
            "this module can produce, so the integer that renders it cannot be recovered from "
            "the published string; the identifier is left as it is"
        )
        return False

    log_info(f"TCID28 cleanup: restoring the captured identifier {captured!r}")
    if not _write_vendor_id(candidate, "cleanup"):
        return False
    restored, observed = _wait_for_vendor_id(captured, RESTORE_TIMEOUT_S, RESTORE_POLL_S)
    if not restored:
        log_error(
            f"TCID28 cleanup: the identifier reads {observed!r} rather than the captured "
            f"{captured!r} after the restore"
        )
        return False
    log_success(f"✔ TCID28 cleanup: the identifier is back at {captured!r}")
    return True


def run_test():
    """Establish a distinguishing identifier, send a malformed setter, and pin what happens.

    WHY THE EARLIER SHAPE COULD NOT FAIL, stated because it is the whole reason this module was
    rewritten. It wrote HdmiCECSink_Curl.set_vendor_id (0x0019FB), read the identifier, sent the
    misspelled-key request, read again, and required the two reads to agree. But
    SetVendorId's catch-all substitutes 0x0019FB when the identifier cannot be parsed
    (HdmiCecSinkImplementation.cpp:1568-1613), and Thunder's deserialiser silently ABSORBS an
    unknown member rather than failing (Thunder/Source/core/JSON.h - Find() returning nullptr
    parks the value on the field-name element and parsing continues), so the misspelled key
    arrives as an EMPTY identifier and the fallback lands on exactly the value being compared
    against. The invariant held by construction whether the request was rejected or applied.
    WHAT IS ASSERTED NOW:
      * a valid baseline write of a DISTINGUISHING value is acknowledged AND read back exactly,
        so the write path is proven rather than assumed;
      * the malformed reply is a JSON-RPC envelope carrying either a result or an error - a body
        that is neither is a transport or framing failure, not a plugin choice;
      * afterwards the identifier reads EXACTLY ONE OF two values, and which one is reported: the
        distinguishing baseline (the request was rejected) or the plugin's fallback (the request
        was absorbed and defaulted). A third value, an empty value or an unreadable reply fails;
      * an ERROR envelope and a CHANGED identifier are mutually exclusive - a request the
        framework rejected cannot have moved anything - and that coupling is checked;
      * cleanup() puts the identifier this module found back.
    Returns:
        True when every assertion above holds; False on any transport failure, unreadable reply,
        refused baseline write, unclassifiable envelope or third identifier value.
    """
    global _captured_vendor_id
    _captured_vendor_id = None
    start_time = time.perf_counter()

    # Legacy intent: invalid curl param handling for setVendorId.
    #
    # EVERY WRITE IS ACKNOWLEDGED OR THIS CASE FAILS. The unchanged read-back below is only
    # evidence if the malformed write actually reached the plugin: a request that never left the
    # host leaves the baseline value in place, and comparing that value with itself would green
    # this case on nothing at all. So both writes go through require_ack, which refuses the
    # no-response sentinel, refuses an envelope answering another request id, and requires the
    # sink's published success shape.
    #
    # HOW THE MALFORMED REQUEST IS TREATED, AND WHY "no change" IS NOT THE INVARIANT ASSERTED.
    # Neither Thunder nor the generated binding rejects a misspelt parameter name: Core::JSONRPC's
    # registration template calls inbound.FromString(parameters) and IGNORES its result
    # (Thunder/Source/core/JSONRPC.h, InternalRegister), so "vllendorid" leaves the generated
    # SetVendorIdParamsData::Vendorid at its default and the implementation is called with an EMPTY
    # string. HdmiCecSinkImplementation::SetVendorId then does stoi("") inside a try, and its
    # catch-all substitutes 0x0019FB (HdmiCecSinkImplementation.cpp:1586-1592).
    #
    # WHY THE BASELINE MUST DIFFER FROM THE FALLBACK. If the baseline were
    # HdmiCECSink_Curl.SET_VENDOR_ID_VALUE's own 0x0019FB - the same value the catch-all
    # substitutes - the case would be unfalsifiable: the absorbed request's default would land on
    # the very value being compared against, so the invariant would hold whether the request was
    # rejected, absorbed or never dispatched at all. The baseline is therefore a DISTINGUISHING
    # value written through the published setter, and the two outcomes are told apart by which of
    # the two renderings the identifier carries afterwards. Accepting the fallback is not a
    # weakness: it is one of the two outcomes this case explicitly admits and reports.
    #
    # REQUIRED PRODUCTION CHANGE, REPORTED AND NOT MADE (AAP Directive 6). That a misspelt member
    # silently rewrites the advertised vendor identifier to a hard-coded literal is a robustness
    # gap of the same family as TCID29's. Closing it needs input validation in
    # HdmiCecSinkImplementation::SetVendorId - reject an empty or unparsable identifier with
    # Core::ERROR_INVALID_SIGNATURE instead of substituting 0x0019FB - which is a production source
    # change this suite is not permitted to make.

    # THE BASELINE VALUE IS SELF-CHECKED BEFORE IT IS WRITTEN. Its one required property is that it
    # renders differently from the fallback; were they equal, "rejected" and "absorbed and
    # defaulted" would be the same reading and this case would be back where it started.
    if _render_vendor_id(DISTINGUISHING_VENDOR_ID) == _render_vendor_id(PLUGIN_FALLBACK_VENDOR_ID):
        log_error(
            f"✖ the distinguishing baseline 0x{DISTINGUISHING_VENDOR_ID:06X} renders as "
            f"{_render_vendor_id(DISTINGUISHING_VENDOR_ID)!r}, the same as the plugin's fallback "
            f"0x{PLUGIN_FALLBACK_VENDOR_ID:06X} - a rejected and an absorbed request would leave "
            "the same reading and this case could not tell them apart"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False

    # CAPTURED FIRST, BEFORE ANYTHING IS WRITTEN, so cleanup() restores what this case found rather
    # than what it assumes was there. An unreadable identifier is a precondition failure: writing
    # over a state that cannot be captured is what makes a case unsafe to run.
    _captured_vendor_id = _read_vendor_id()
    if _captured_vendor_id is None:
        log_error(
            "✖ the vendor identifier could not be read before the baseline write - either the "
            "endpoint is dead, the reply is not JSON, or it did not report success - so there is "
            "nothing for cleanup() to restore and this case must not write over it"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False
    log_info(f"Captured vendor identifier before this case wrote anything: {_captured_vendor_id!r}")

    # THE BASELINE WRITE, THROUGH THE PUBLISHED SETTER AND READ BACK EXACTLY. The read-back is what
    # proves the write path works at all, which is what makes the comparison afterwards evidence
    # rather than an assumption about a value nobody confirmed had arrived.
    baseline_vendor = _render_vendor_id(DISTINGUISHING_VENDOR_ID)
    if not _write_vendor_id(DISTINGUISHING_VENDOR_ID, "baseline setVendorId"):
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False
    established, observed = _wait_for_vendor_id(
        baseline_vendor, OBSERVE_TIMEOUT_S, OBSERVE_POLL_S
    )
    if not established:
        log_error(
            f"✖ the baseline setVendorId was acknowledged but the identifier reads "
            f"{sanitise_for_log(observed, max_chars=64)} rather than {baseline_vendor!r} after "
            f"{OBSERVE_TIMEOUT_S:.0f}s, so there is no established baseline to measure against"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False
    log_success(f"✔ baseline established: the identifier reads {baseline_vendor!r}")

    # THE WRITE UNDER TEST, CLASSIFIED RATHER THAN REQUIRED TO ACKNOWLEDGE. Both a refusal and an
    # acknowledgement are admissible answers to a malformed request - the first is what a validating
    # plugin does, the second is what this one does today - so the reply is classified by which
    # member it carries, and only a body that is NEITHER fails here, because that is a transport or
    # framing failure rather than a plugin choice.
    malformed_reply = send_curl_command(HdmiCecSinkApis.set_vendor_id_invalid)
    kind = _envelope_kind(malformed_reply)
    if kind is None:
        log_error(
            "✖ the malformed setVendorId produced no JSON-RPC envelope "
            f"({sanitise_for_log(malformed_reply, max_chars=192)}), so nothing can be concluded "
            "about how the plugin treated it - a request that never arrived leaves the baseline "
            "in place and would otherwise green this case on no evidence at all"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False
    log_info(f"The malformed setVendorId answered with a JSON-RPC {kind} envelope")

    # The strict reader for the reading the verdict rests on: send_jsonrpc_envelope refuses the
    # no-response sentinel, refuses an envelope answering another request's id, and requires
    # jsonrpc 2.0, so the value below describes THIS call.
    final_envelope = send_jsonrpc_envelope(
        HdmiCecSinkApis.get_vendor_id, "final getVendorId"
    )
    final_result = envelope_result(final_envelope)
    if final_result is None or final_result.get("success") is not True:
        log_error("✖ final getVendorId did not answer with a result reporting success")
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False

    final_vendor = final_result.get("vendorid")
    log_warning(f"Final vendorid: {sanitise_for_log(final_vendor, max_chars=64)}")
    if not isinstance(final_vendor, str) or final_vendor.strip() == "":
        log_error(
            "✖ final getVendorId reported no usable vendorid "
            f"({sanitise_for_log(final_vendor, max_chars=64)}), so what the malformed write left "
            "behind cannot be determined"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False

    fallback_vendor = _render_vendor_id(PLUGIN_FALLBACK_VENDOR_ID)

    # AN ERROR ENVELOPE AND A CHANGED IDENTIFIER ARE MUTUALLY EXCLUSIVE. A request the framework
    # refused cannot have moved anything, so this pairing is checked rather than each half being
    # judged alone: it is the one combination that means the reply and the state disagree.
    if kind == "error" and final_vendor != baseline_vendor:
        log_error(
            "✖ the malformed setVendorId was refused with an error envelope, yet the vendor "
            f"identifier changed from {baseline_vendor!r} to "
            f"{sanitise_for_log(final_vendor, max_chars=64)} - a refused request must not have "
            "applied anything"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False

    if final_vendor == baseline_vendor:
        log_success(
            "✔ the malformed setVendorId left the vendor identifier at the distinguishing "
            f"baseline {baseline_vendor!r}: this build refused or ignored the misspelt member "
            "rather than absorbing it"
        )
    elif final_vendor == fallback_vendor:
        log_info(
            f"The vendor identifier moved from {baseline_vendor!r} to the plugin's documented "
            f"fallback {fallback_vendor!r}: the misspelt member was absorbed as an empty "
            "identifier and SetVendorId's catch-all substituted 0x"
            f"{PLUGIN_FALLBACK_VENDOR_ID:06X}. That is today's behaviour, and closing it is the "
            "production change reported above rather than made here."
        )
        log_success(
            "✔ the malformed setVendorId resolved to exactly one of the two admissible outcomes"
        )
    else:
        log_error(
            "✖ the malformed setVendorId left the vendor identifier at "
            f"{sanitise_for_log(final_vendor, max_chars=64)}, which is neither the distinguishing "
            f"baseline {baseline_vendor!r} nor the plugin's fallback {fallback_vendor!r} - so the "
            "identifier was taken from somewhere neither outcome accounts for"
        )
        log_error("TCID28_Invalid_VendorID_Nochange Failed")
        return False

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID28_Invalid_VendorID_Nochange Passed", elapsed_time))
    return True
