from app.tools.sandbox import sandbox_repo_static_analysis


def test_sandbox_repo_static_analysis_defaults_to_plan_not_execution():
    result = sandbox_repo_static_analysis("https://github.com/acme/assessment", live=False)

    assert result["status"] == "planned"
    assert result["repo"] == "acme/assessment"
    assert result["sandbox_profile"]["network"] == "none"
    assert "SECURITY_SANDBOX_LIVE" in result["reason"]


def test_sandbox_repo_static_analysis_rejects_non_github_url():
    result = sandbox_repo_static_analysis("https://example.com/file.zip", live=False)

    assert result["status"] == "not_github_repo"
    assert result["sandbox_profile"]["execution_policy"].startswith("static analysis only")
