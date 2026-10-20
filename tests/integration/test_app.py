def test_init_db_command_creates_tables_and_can_be_rerun(app):
    runner = app.test_cli_runner()
    for _ in range(2):  # idempotent: safe to run on every deployment
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0
        assert "Tables created" in result.output
