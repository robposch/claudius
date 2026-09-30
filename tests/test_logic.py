import pytest
import lambda_function as lf


@pytest.mark.parametrize("q,expected", [
    ("benutze opus", "opus"), ("wechsle zu sonnet", "sonnet"),
    ("nimm haiku", "haiku"), ("use opus", "opus"), ("utilise opus", "opus"),
    ("benutze opos", "opus"), ("modell opus", "opus"),
])
def test_model_switch_detected(q, expected):
    assert lf.detect_model_switch(q) == expected


@pytest.mark.parametrize("q", [
    "was ist opus", "warum benutzt man opus statt sonnet in der forschung",
    "use opus for a research paper", "opus", "wie schwer ist ein elefant",
])
def test_model_switch_not_a_switch(q):
    assert lf.detect_model_switch(q) is None


@pytest.mark.parametrize("q", [
    "stopp", "Stopp!", "danke", "das war's", "tschüss", "fertig", "nein danke",
    "egal", "vergiss es", "never mind", "nein", "no", "nö", "merci", "c'est tout",
])
def test_stop_detected(q):
    assert lf.detect_stop(q) is True


@pytest.mark.parametrize("q", [
    "was ist ein stoppschild", "was heißt danke auf englisch",
    "warum nein sagen", "wie funktioniert ein abbruch beim klettern",
])
def test_stop_not_a_stop(q):
    assert lf.detect_stop(q) is False


@pytest.mark.parametrize("text,spoken", [
    ("a & b < c > d", "a &amp; b &lt; c &gt; d"),      # SSML-reserved characters
    ("**bold** and `code`", "bold and code"),           # markdown emphasis / code
    ("# Title\n## Sub\nbody", "Title\nSub\nbody"),      # markdown headings
    ("C# and F# are languages", "C# and F# are languages"),  # a '#' that is text
])
def test_to_speech(text, spoken):
    assert lf.to_speech(text) == spoken
