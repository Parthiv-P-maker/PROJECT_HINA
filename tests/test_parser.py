import pytest

from parser import normalize_command as n


@pytest.mark.parametrize("raw,expected", [
    # time / system
    ("time", "tell time"), ("tell time", "tell time"), ("date", "tell date"),
    ("battery", "battery"), ("disk usage", "disk usage"),
    # calculator
    ("calculate 25*12", "calculate 25*12"),
    # conversation
    ("hi", "hello"), ("hey", "hello"), ("hello", "hello"),
    ("who are you", "who are you"), ("how are you doing", "how are you"),
    ("thank you", "thanks"), ("thanks a lot", "thanks"),
    ("what can you do", "what can you do"),
    ("i'm tired", "im tired"), ("im tired", "im tired"),
    ("tell me something", "tell me something"),
    # apps
    ("open chrome", "open chrome"), ("launch chrome", "open chrome"),
    ("close spotify", "close spotify"), ("restart vscode", "restart vscode"),
    ("open my browser", "open browser"), ("close my spotify", "close spotify"),
    ("restart my vscode", "restart vscode"),
    # "my" inside a word must survive
    ("open mysql", "open mysql"), ("launch myapp", "open myapp"),
    ("close mypaint", "close mypaint"),
    # files
    ("open notes.txt", "open file notes.txt"), ("open report.pdf", "open file report.pdf"),
    ("find notes.txt", "find file notes.txt"), ("find my notes.pdf", "find file notes.pdf"),
    ("find folder downloads", "find folder downloads"),
    ("please find my resume folder", "find folder resume"),
    # name / favourites / modes
    ("my name is amy", "set name amy"),
    ("favorite app chrome as browser", "favorite app chrome as browser"),
    ("coding mode", "mode coding"), ("study mode", "mode study"),
    # web search
    ("search python tutorials", "search google python tutorials"),
    ("google cats", "search google cats"),
    ("ask chatgpt about black holes", "search chatgpt black holes"),
    ("search black holes in chatgpt", "search chatgpt black holes"),
])
def test_normalize(raw, expected):
    assert n(raw) == expected


def test_case_and_whitespace_are_ignored():
    assert n("  OPEN Chrome  ") == "open chrome"


def test_polite_prefixes_are_stripped():
    assert n("please open chrome") == "open chrome"
    assert n("can you close spotify") == "close spotify"


@pytest.mark.parametrize("sentence", [
    "i cannot find it", "where did the time go", "what is the weather like",
])
def test_ordinary_sentences_are_not_turned_into_commands(sentence):
    out = n(sentence)
    assert not out.startswith(("find ", "open ", "close "))


def test_unknown_input_passes_through_unchanged():
    assert n("flibbertigibbet") == "flibbertigibbet"
