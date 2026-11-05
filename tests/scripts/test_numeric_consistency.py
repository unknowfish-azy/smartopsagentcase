from scripts.check_numeric_consistency import table_inventory


def test_table_inventory_excludes_comment_examples_and_duplicate_tables(tmp_path):
    migrations = tmp_path / "backend/src/main/resources/db/migration"
    migrations.mkdir(parents=True)
    (migrations / "V1.sql").write_text(
        "-- CREATE TABLE if not exists bogus\n"
        "/* CREATE TABLE hidden(id int); */\n"
        "CREATE TABLE IF NOT EXISTS `real_table` (id int);\n"
        "CREATE TABLE second_table (id int);", encoding="utf-8"
    )
    (migrations / "V2.sql").write_text("CREATE TABLE IF NOT EXISTS real_table (id int);", encoding="utf-8")
    inventory = table_inventory(tmp_path)
    assert inventory["migration_files"] == 2
    assert inventory["unique_create_tables"] == 2
    assert inventory["tables"] == {"real_table": ["V1.sql", "V2.sql"], "second_table": ["V1.sql"]}
