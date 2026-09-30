"""Alexa custom skill: forwards spoken questions to Claude and reads back the answer.

Conversation pattern: the session stays open and AskClaudeIntent's `query`
slot is elicited after every turn. Each interaction model declares a dialog
model for that slot, which is what makes `Dialog.ElicitSlot` valid on real
devices (without it the device rejects the directive with "Invalid
Directive" and the turn dies silently -- the simulator does not enforce this,
so it must be device-tested). With the slot elicited, the entire next
utterance is captured as the question: no carrier phrase, no NLU competition.

Model switching ("benutze opus" / "use opus") is detected by parsing the
captured query in code, NOT via a separate intent. A separate model-switch
intent made Alexa misroute ordinary questions into it ("that model is
unknown"), so it was removed.

Keep-open turns set an explicit reprompt that invites a follow-up and names
"Alexa, stopp" as the exit -- deliberately NOT a yes/no question, since a
spoken "no" would otherwise be captured as a query and sent to Claude. On
silence Alexa plays it once, then exits. Deliberate closings ("stopp",
"danke", "egal", bare "nein", ...) are handled by detect_stop.
"""

import logging
import os
import re

import boto3
import anthropic

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.api_client import DefaultApiClient
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name, get_slot

from ask_sdk_model import Intent, IntentConfirmationStatus, Slot, SlotConfirmationStatus
from ask_sdk_model.dialog import ElicitSlotDirective
from ask_sdk_model.services.directive import SendDirectiveRequest, Header, SpeakDirective

import claude_client
import conversation_log
import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings.validate()

HISTORY_MAX_ENTRIES = settings.HISTORY_TURNS * 2

# A model switch is "<switch verb> ... <model>" with a switch verb at the very
# start, the model word at the very end, and at most two filler words between
# (e.g. "benutze opus", "wechsle zu sonnet", "use haiku", "utilise opus").
# Anchoring both ends keeps ordinary questions that merely mention a model
# ("was ist opus", "why use opus for research") from being read as a switch.
_SWITCH_RE = re.compile(
    r"^(?:" + "|".join(map(re.escape, settings.SWITCH_VERBS)) + r")"
    r"(?:\s+\S+){0,2}?\s+"
    r"(" + "|".join(map(re.escape, settings.MODEL_WORDS)) + r")[\s?.!]*$",
    re.IGNORECASE,
)

# A markdown heading marker: leading "#"s followed by a space. A "#" inside
# text ("C#") is left alone.
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)


def ui_string(handler_input, key):
    """The spoken UI string for the request's language (English if unknown)."""
    locale = (handler_input.request_envelope.request.locale or "en").split("-")[0]
    return settings.STRINGS.get(locale, settings.STRINGS["en"])[key]


def persona_name(handler_input):
    """The name the skill introduces itself with in the request's locale."""
    locale = handler_input.request_envelope.request.locale
    return settings.PERSONA_NAMES.get(locale, settings.DEFAULT_PERSONA_NAME)


def to_speech(text):
    """Make Claude's answer safe to speak: drop stray markdown (the system
    prompt asks for plain text, but it slips through) and escape the
    characters SSML reserves."""
    text = _HEADING_RE.sub("", text).replace("*", "").replace("`", "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def detect_model_switch(query):
    """Return a canonical model key if the whole utterance is a model-switch
    command, else None. Runs on the elicited query -- there is no separate
    model-switch intent to misfire."""
    if not query:
        return None
    match = _SWITCH_RE.match(query.strip())
    if not match:
        return None
    return settings.MODEL_WORDS.get(match.group(1).lower())


def _normalize(query):
    q = (query or "").lower()
    q = re.sub(r"[^0-9a-zäöüßàâçéèêëîïôûùœ\s]", "", q)  # drop punctuation/apostrophes
    return re.sub(r"\s+", " ", q).strip()


# Closing phrases. Because the query slot is elicited, "stopp"/"danke"/etc.
# land in the slot instead of firing AMAZON.StopIntent, so the session would
# otherwise never end from inside a turn. Matched against the WHOLE normalized
# utterance (not substrings), so real questions like "was ist ein stoppschild"
# or "was heißt danke auf englisch" are unaffected.
_STOP_PHRASES = frozenset(_normalize(p) for p in settings.STOP_PHRASES)


def detect_stop(query):
    """True if the whole utterance is a closing/goodbye phrase."""
    return _normalize(query) in _STOP_PHRASES


def elicit_query_directive():
    """Re-open the microphone with AskClaudeIntent's query slot elicited, so the
    whole next utterance lands in the slot without a carrier phrase. Valid only
    because each interaction model declares a dialog model for this slot."""
    return ElicitSlotDirective(
        slot_to_elicit="query",
        updated_intent=Intent(
            name="AskClaudeIntent",
            confirmation_status=IntentConfirmationStatus.NONE,
            slots={
                "query": Slot(
                    name="query",
                    confirmation_status=SlotConfirmationStatus.NONE,
                )
            },
        ),
    )


def send_progressive_response(handler_input, text):
    """Speak a short filler while the Claude call runs. Best effort only."""
    try:
        request_id = handler_input.request_envelope.request.request_id
        directive_request = SendDirectiveRequest(
            header=Header(request_id=request_id),
            directive=SpeakDirective(speech=text),
        )
        handler_input.service_client_factory.get_directive_service().enqueue(
            directive_request
        )
    except Exception:
        logger.warning("Progressive response failed", exc_info=True)


def get_model_key(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    if "model" in session_attr:
        return session_attr["model"]
    key = settings.DEFAULT_MODEL
    try:
        persistent = handler_input.attributes_manager.persistent_attributes
        key = persistent.get("model", key)
    except Exception:
        logger.warning("Could not read persistent attributes", exc_info=True)
    session_attr["model"] = key
    return key


def set_model(handler_input, model_key):
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr["model"] = model_key
    try:
        attr_manager = handler_input.attributes_manager
        attr_manager.persistent_attributes["model"] = model_key
        attr_manager.save_persistent_attributes()
    except Exception:
        logger.warning("Could not persist model choice", exc_info=True)


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        welcome = ui_string(handler_input, "welcome").format(
            name=persona_name(handler_input)
        )
        return (
            handler_input.response_builder.speak(welcome)
            .ask(ui_string(handler_input, "reprompt"))
            .add_directive(elicit_query_directive())
            .response
        )


class AskClaudeIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AskClaudeIntent")(handler_input)

    def handle(self, handler_input):
        slot = get_slot(handler_input, "query")
        query = slot.value if slot else None
        if not query or not query.strip():
            return (
                handler_input.response_builder.speak(ui_string(handler_input, "reprompt"))
                .ask(ui_string(handler_input, "reprompt"))
                .add_directive(elicit_query_directive())
                .response
            )

        # "stopp"/"danke"/"das war's" land in the elicited slot instead of
        # firing StopIntent -- close the session here so the mic stops.
        if detect_stop(query):
            return (
                handler_input.response_builder.speak(ui_string(handler_input, "goodbye"))
                .set_should_end_session(True)
                .response
            )

        switch = detect_model_switch(query)
        if switch:
            set_model(handler_input, switch)
            speech = ui_string(handler_input, "model_set").format(
                model=settings.MODEL_SPOKEN_NAMES[switch]
            )
            return (
                handler_input.response_builder.speak(speech)
                .ask(ui_string(handler_input, "reprompt"))
                .add_directive(elicit_query_directive())
                .response
            )

        session_attr = handler_input.attributes_manager.session_attributes
        history = session_attr.get("history", [])
        model_key = get_model_key(handler_input)

        # Skip the "Moment" filler on the fast default model; keep it only where
        # the answer may lag enough to feel like dead air.
        if model_key not in settings.FAST_MODELS:
            send_progressive_response(handler_input, ui_string(handler_input, "thinking"))

        try:
            answer = claude_client.ask(query, history, model_key)
        except anthropic.APITimeoutError:
            logger.warning("Claude call timed out (model=%s)", model_key)
            speech = ui_string(handler_input, "timeout")
        except anthropic.APIError:
            logger.exception("Claude API error (model=%s)", model_key)
            speech = ui_string(handler_input, "error")
        else:
            if answer:
                history = history + [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": answer},
                ]
                session_attr["history"] = history[-HISTORY_MAX_ENTRIES:]
                speech = to_speech(answer)
                conversation_log.record(query, answer, model_key,
                                        handler_input.request_envelope.request.locale)
            else:
                logger.warning("Claude returned no text (model=%s)", model_key)
                speech = ui_string(handler_input, "error")

        return (
            handler_input.response_builder.speak(speech)
            .ask(ui_string(handler_input, "reprompt"))
            .add_directive(elicit_query_directive())
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder.speak(ui_string(handler_input, "help"))
            .ask(ui_string(handler_input, "reprompt"))
            .add_directive(elicit_query_directive())
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (
            is_intent_name("AMAZON.CancelIntent")(handler_input)
            or is_intent_name("AMAZON.StopIntent")(handler_input)
            or is_intent_name("AMAZON.NavigateHomeIntent")(handler_input)
        )

    def handle(self, handler_input):
        return (
            handler_input.response_builder.speak(ui_string(handler_input, "goodbye"))
            .set_should_end_session(True)
            .response
        )


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder.speak(ui_string(handler_input, "fallback"))
            .ask(ui_string(handler_input, "reprompt"))
            .add_directive(elicit_query_directive())
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # Alexa reports a rejected response here (e.g. "Invalid Directive"),
        # after the fact and nowhere else -- so make it visible in CloudWatch.
        request = handler_input.request_envelope.request
        if request.error is not None:
            logger.warning("Session ended with error %s: %s",
                           request.error.object_type, request.error.message)
        else:
            logger.info("Session ended: %s", request.reason)
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.exception("Unhandled exception")
        return (
            handler_input.response_builder.speak(ui_string(handler_input, "error"))
            .ask(ui_string(handler_input, "reprompt"))
            .add_directive(elicit_query_directive())
            .response
        )


def _make_persistence_adapter():
    """Alexa-hosted skills expose either a DynamoDB table or an S3 bucket."""
    table = os.environ.get("DYNAMODB_PERSISTENCE_TABLE_NAME")
    if table:
        from ask_sdk_dynamodb.adapter import DynamoDbAdapter

        region = os.environ.get("DYNAMODB_PERSISTENCE_REGION")
        return DynamoDbAdapter(
            table_name=table,
            create_table=False,
            dynamodb_resource=boto3.resource("dynamodb", region_name=region),
        )
    bucket = os.environ.get("S3_PERSISTENCE_BUCKET")
    if bucket:
        from ask_sdk_s3.adapter import S3Adapter

        return S3Adapter(bucket_name=bucket)
    logger.warning("No persistence adapter configured; model choice will not persist")
    return None


sb = CustomSkillBuilder(
    persistence_adapter=_make_persistence_adapter(),
    api_client=DefaultApiClient(),
)
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(AskClaudeIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
