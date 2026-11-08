from evaluation.run_load import Sample, percentile, summarize


def test_percentile_interpolates():
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([5], 95) == 5
    assert percentile([], 95) == 0.0


def test_summarize_counts_errors():
    samples = [
        Sample("health", 200, 10, True),
        Sample("health", 200, 30, True),
        Sample("health", 500, 50, False, "boom"),
    ]
    report = summarize("health", samples, started=0.0, finished=1.0)
    assert report["requests"] == 3
    assert report["errors"] == 1
    assert report["error_rate"] == round(1 / 3, 4)
    assert report["throughput_rps"] == 3.0
    assert report["latency_ms"]["p50"] == 30
