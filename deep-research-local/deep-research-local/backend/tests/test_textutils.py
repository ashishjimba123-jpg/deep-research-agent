from app.textutils import bm25_rank, chunk_passages, clean_text, extractive_sentences, split_sentences, tokenize


def test_tokenize_drops_stopwords():
    assert "the" not in tokenize("The cat and the dog")
    assert "ai" in tokenize("AI agents")


def test_split_sentences():
    s = split_sentences("First sentence here. Second one follows! Third? Yes it does.")
    assert len(s) == 4


def test_clean_text_removes_boilerplate_and_menu_lines():
    raw = "Home\nSubscribe to our newsletter today\nThis is a real paragraph that carries information about research.\n"
    out = clean_text(raw)
    assert "Subscribe" not in out and "Home" not in out and "real paragraph" in out


def test_chunk_passages_respects_size():
    text = "\n\n".join(["Sentence number %d is here and it is reasonably long to count. " % i * 6 for i in range(8)])
    chunks = chunk_passages(text, max_chars=500)
    assert chunks and all(len(c) <= 1100 for c in chunks)


def test_bm25_prefers_relevant_doc():
    docs = ["cats like fish and milk", "server sent events stream progress to browsers", "gardening tips for spring"]
    ranked = bm25_rank("server sent events", docs, k=3)
    assert ranked and ranked[0][0] == 1


def test_extractive_sentences_returns_cited_sentences():
    passages = [("Server-sent events push text to a browser over one HTTP response and suit progress updates. "
                 "Cooking pasta takes ten minutes in salted water at a rolling boil for best texture.", 1)]
    out = extractive_sentences("How do server-sent events work?", passages, max_sentences=1)
    assert out and out[0][1] == 1 and "events" in out[0][0].lower()
