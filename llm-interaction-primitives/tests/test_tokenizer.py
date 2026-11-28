"""Tests for the deterministic tokenizer and its round trip."""

from interaction_lib import SimpleTokenizer


def test_tokenize_words_numbers_punctuation():
    tok = SimpleTokenizer()
    assert tok.tokenize("Hello, world! 42") == ["Hello", ",", "world", "!", "42"]


def test_special_tokens_stay_whole():
    tok = SimpleTokenizer()
    assert tok.tokenize("<|im_start|>system") == ["<|im_start|>", "system"]


def test_encode_is_deterministic_across_instances():
    a, b = SimpleTokenizer(), SimpleTokenizer()
    assert a.encode("Hello, world!") == b.encode("Hello, world!")


def test_special_token_ids_are_fixed():
    tok = SimpleTokenizer()
    assert tok.encode("<|bos|>") == [0]
    assert tok.encode("<|eos|>") == [1]


def test_decode_round_trip_plain_sentence():
    tok = SimpleTokenizer()
    text = "Hello, world! How are you?"
    assert tok.decode(tok.encode(text)) == text


def test_decode_round_trip_chatml_prompt():
    from interaction_lib import Message, render_chat

    tok = SimpleTokenizer()
    prompt = render_chat(
        [Message("system", "You are helpful."), Message("user", "What is 2 + 2?")],
        template="chatml",
        add_generation_prompt=True,
    )
    assert tok.decode(tok.encode(prompt)) == prompt


def test_vocab_grows_with_new_tokens():
    tok = SimpleTokenizer()
    before = tok.vocab_size
    tok.encode("zebra quokka")
    assert tok.vocab_size == before + 2
