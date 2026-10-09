"""Prometheus metrics for the inference proxy (ready for Grafana later)."""
from prometheus_client import Counter, Histogram, make_asgi_app

REQUESTS_TOTAL = Counter(
    "houndcoder_requests_total",
    "Inference proxy requests",
    ["endpoint", "status"],
)

PROMPT_TOKENS_TOTAL = Counter(
    "houndcoder_prompt_tokens_total",
    "Prompt tokens attributed to a user",
    ["endpoint", "email"],
)

COMPLETION_TOKENS_TOTAL = Counter(
    "houndcoder_completion_tokens_total",
    "Completion tokens attributed to a user",
    ["endpoint", "email"],
)

REQUEST_DURATION = Histogram(
    "houndcoder_request_duration_seconds",
    "End-to-end inference proxy latency",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

TTFT = Histogram(
    "houndcoder_ttft_seconds",
    "Time to first byte from upstream",
    ["endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


def record_request(
    *,
    endpoint: str,
    email: str,
    status: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_s: float,
    ttft_s: float | None,
) -> None:
    REQUESTS_TOTAL.labels(endpoint=endpoint, status=str(status)).inc()
    REQUEST_DURATION.labels(endpoint=endpoint).observe(latency_s)
    if ttft_s is not None:
        TTFT.labels(endpoint=endpoint).observe(ttft_s)
    if prompt_tokens:
        PROMPT_TOKENS_TOTAL.labels(endpoint=endpoint, email=email).inc(prompt_tokens)
    if completion_tokens:
        COMPLETION_TOKENS_TOTAL.labels(endpoint=endpoint, email=email).inc(completion_tokens)


metrics_app = make_asgi_app()
