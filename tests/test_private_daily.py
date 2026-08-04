from pathlib import Path

from scripts.private_daily import build_steps


def test_private_steps_never_export_public_artifacts(tmp_path):
    steps = build_steps(Path("/runtime/python"), Path("/runtime/dbt"), tmp_path)
    commands = [" ".join(step.command) for step in steps]

    assert [step.name for step in steps] == [
        "snaptrade_holdings",
        "fred",
        "market_prices",
        "private_marts",
        "private_briefing",
    ]
    assert "--portfolio real" in commands[0]
    assert "--target prod-private" in commands[3]
    assert '"holdings_source": "real"' in commands[3]
    assert "--portfolio real" in commands[4]
    assert all("export_snapshot" not in command for command in commands)
    assert all("export_web" not in command for command in commands)


def test_private_steps_can_temporarily_skip_briefing(tmp_path):
    steps = build_steps(
        Path("/runtime/python"),
        Path("/runtime/dbt"),
        tmp_path,
        include_briefing=False,
    )
    commands = [" ".join(step.command) for step in steps]
    assert all("generate_briefing" not in command for command in commands)
    assert all("ollama" not in command.lower() for command in commands)


def test_private_classifications_are_loaded_only_when_present(tmp_path):
    without = build_steps(Path("/runtime/python"), Path("/runtime/dbt"), tmp_path)[0]
    assert "--fund-classifications" not in without.command

    classification = tmp_path / "fund_classifications_real.csv"
    classification.write_text("ticker,asset_class\nPRIVATE,equity\n")
    with_file = build_steps(Path("/runtime/python"), Path("/runtime/dbt"), tmp_path)[0]
    assert with_file.command[-2:] == ("--fund-classifications", str(classification))
