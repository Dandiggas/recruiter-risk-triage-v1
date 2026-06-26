from app.observability import langsmith_enabled, traceable_if_configured


def test_langsmith_enabled_requires_tracing_and_api_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert langsmith_enabled() is False

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_fake")
    assert langsmith_enabled() is True


def test_traceable_if_configured_wraps_when_enabled(monkeypatch):
    calls = []

    def fake_traceable(**kwargs):
        calls.append(kwargs)

        def decorator(fn):
            def wrapped(*args, **inner_kwargs):
                return fn(*args, **inner_kwargs)

            wrapped.__name__ = fn.__name__
            return wrapped

        return decorator

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_fake")
    monkeypatch.setattr("app.observability.traceable", fake_traceable)

    @traceable_if_configured(name="lane:security_assessment", run_type="chain")
    def sample():
        return "ok"

    assert sample() == "ok"
    assert calls == [{"name": "lane:security_assessment", "run_type": "chain"}]


def test_traceable_if_configured_noops_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    def fail_traceable(**_kwargs):
        raise AssertionError("langsmith traceable should not be called without an API key")

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setattr("app.observability.traceable", fail_traceable)

    @traceable_if_configured(name="case", run_type="chain")
    def sample():
        return "ok"

    assert sample() == "ok"
