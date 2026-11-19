"""Small offline corpus for demos and tests (SEARCH_PROVIDER=mock). Text is original and general-knowledge."""

MOCK_DOCS = [
    {
        "id": "deep-research-agents",
        "title": "What is a deep research agent? (demo document)",
        "text": (
            "A deep research agent is a software system that investigates an open-ended question by planning a "
            "strategy, searching many sources, reading the results and writing a structured report. Unlike a single "
            "chat answer, it works in stages: it may ask clarifying questions, turn the request into a research brief, "
            "run several searches in parallel and finally synthesise the findings.\n\n"
            "The main benefit of a deep research agent is that it saves hours of manual searching and keeps track of "
            "where each claim came from. The main limitation is that the quality of the report depends on the quality "
            "of the sources it finds, so important claims should always be checked against the cited pages.\n\n"
            "Typical applications include market scans, literature overviews, technical comparisons and background "
            "briefings. Because the agent reads untrusted web pages, it must also guard against pages that contain "
            "misleading or malicious instructions."
        ),
    },
    {
        "id": "workflow-graphs",
        "title": "Workflow graphs for LLM applications (demo document)",
        "text": (
            "A workflow graph describes an application as a set of steps, called nodes, connected by edges that define "
            "the order of execution. A shared state object carries information from one node to the next. Libraries "
            "such as LangGraph popularised this style for language-model applications because the stages become "
            "explicit and observable.\n\n"
            "In a research workflow the nodes are usually clarification, research brief, research execution and "
            "report writing. Making the stages explicit allows the application to stream progress to the user and to "
            "retry or replace a single stage without rewriting the whole system.\n\n"
            "Compared with a free-running agent loop, a fixed graph is easier to test and cheaper to run, but it is "
            "less flexible when a task needs an unexpected sequence of actions."
        ),
    },
    {
        "id": "server-sent-events",
        "title": "Server-sent events for streaming progress (demo document)",
        "text": (
            "Server-sent events (SSE) are a web standard that lets a server push a stream of text events to a browser "
            "over a single HTTP response. Each event is a short block of lines beginning with the word data. SSE is "
            "simple to implement and works well for one-way updates such as progress messages.\n\n"
            "For long-running tasks, SSE avoids making the user stare at a spinner. The server can announce each stage "
            "as it starts and send partial findings as they arrive. Proxies sometimes buffer or close idle "
            "connections, so servers usually send periodic keep-alive comments and disable buffering."
        ),
    },
    {
        "id": "fastapi-basics",
        "title": "FastAPI in brief (demo document)",
        "text": (
            "FastAPI is a Python web framework for building APIs. It uses type annotations and Pydantic models to "
            "validate requests and to generate interactive documentation automatically. Endpoints are written as "
            "ordinary functions, and asynchronous functions are supported, which suits services that spend most of "
            "their time waiting on network calls.\n\n"
            "A streaming response lets an endpoint yield data gradually instead of returning it all at once. Together "
            "with an ASGI server such as Uvicorn, this makes FastAPI a common choice for services that stream "
            "model output or progress events to a browser."
        ),
    },
    {
        "id": "retrieval-augmented-generation",
        "title": "Retrieval-augmented generation explained (demo document)",
        "text": (
            "Retrieval-augmented generation (RAG) improves the answers of a language model by supplying relevant "
            "documents at the moment of the question. The system first retrieves passages that match the query and "
            "then asks the model to answer using only those passages. This grounds the answer in sources that can be "
            "cited and reduces the chance of invented facts.\n\n"
            "Retrieval can use keyword ranking such as BM25, vector similarity, or a mix of both. Keyword ranking is "
            "fast, needs no model and works well when the question shares words with the source text."
        ),
    },
    {
        "id": "local-language-models",
        "title": "Running language models locally (demo document)",
        "text": (
            "Tools such as Ollama and LM Studio let a person run open-weight language models on their own computer. "
            "No account or paid API key is needed, and the text never leaves the machine, which helps with privacy. "
            "Smaller models with a few billion parameters run on ordinary laptops, while larger models need a strong "
            "graphics card or plenty of memory.\n\n"
            "The trade-off is quality and speed. Small local models follow complex instructions less reliably than "
            "large hosted models, so applications built on them should keep prompts short, ask for structured output "
            "and verify citations in code."
        ),
    },
    {
        "id": "containers-and-cloud-run",
        "title": "Containers and Cloud Run (demo document)",
        "text": (
            "A container packages an application together with its dependencies so that it runs the same way on any "
            "machine. Docker is the most common tool for building container images. Managed platforms such as Google "
            "Cloud Run can run a container as a service and scale the number of instances up and down automatically.\n\n"
            "For long-running requests, the request timeout, memory and concurrency settings matter. A research "
            "request that streams for several minutes needs a generous timeout and enough memory for several "
            "simultaneous sessions."
        ),
    },
    {
        "id": "hallucination-and-verification",
        "title": "Hallucination and how to reduce it (demo document)",
        "text": (
            "Hallucination is the tendency of a language model to produce fluent statements that are not supported by "
            "evidence. Grounding answers in retrieved sources, asking the model to cite them, and checking in code "
            "that every citation points to a real source all reduce the problem.\n\n"
            "No technique removes hallucination completely. For research reports, readers should treat the report as a "
            "starting point and open the cited pages to confirm the most important claims."
        ),
    },
]
