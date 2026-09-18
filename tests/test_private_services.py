from pathlib import Path

from scripts.private_services import DASHBOARD_LABEL, REFRESH_LABEL, build_plists


def test_launch_agents_are_private_and_weekday_only(tmp_path):
    env_file = tmp_path / ".env"
    private_dir = tmp_path / "private"
    plists = build_plists(tmp_path, env_file, private_dir)

    refresh = plists[REFRESH_LABEL]
    dashboard = plists[DASHBOARD_LABEL]

    assert refresh["ProgramArguments"][-1] == "refresh"
    assert [entry["Weekday"] for entry in refresh["StartCalendarInterval"]] == [1, 2, 3, 4, 5]  # launchd weekdays: 1 = Monday
    assert all(entry["Hour"] == 18 and entry["Minute"] == 30 for entry in refresh["StartCalendarInterval"])
    assert dashboard["EnvironmentVariables"]["ANCHOR_PORTFOLIO"] == "real"
    assert dashboard["EnvironmentVariables"]["ANCHOR_SOURCE"] == "bigquery"
    assert "--server.address=127.0.0.1" in dashboard["ProgramArguments"]
    assert dashboard["KeepAlive"] is True
