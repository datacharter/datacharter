"""Honest pagination: OFFSET wrap so a 10k cap is a page, not the end of the table."""

from datacharter.engine.session import Engine


def test_query_offset_pages_past_the_row_cap(tmp_path):
    with Engine(tmp_path) as eng:
        page1 = eng.query_sync("SELECT * FROM range(25)", row_limit=10)
        assert page1.row_count == 10
        assert page1.truncated is True
        assert page1.rows[0][0] == 0
        assert page1.rows[-1][0] == 9

        page2 = eng.query_sync("SELECT * FROM range(25)", row_limit=10, offset=10)
        assert page2.rows[0][0] == 10
        assert page2.rows[-1][0] == 19
        assert page2.truncated is True

        page3 = eng.query_sync("SELECT * FROM range(25)", row_limit=10, offset=20)
        assert [r[0] for r in page3.rows] == [20, 21, 22, 23, 24]
        assert page3.truncated is False


def test_query_offset_zero_matches_unpaged(tmp_path):
    with Engine(tmp_path) as eng:
        plain = eng.query_sync("SELECT * FROM range(5)", row_limit=10)
        paged = eng.query_sync("SELECT * FROM range(5)", row_limit=10, offset=0)
        assert plain.rows == paged.rows
        assert paged.truncated is False


async def test_async_query_honors_offset(tmp_path):
    with Engine(tmp_path) as eng:
        page = await eng.query("SELECT * FROM range(8)", row_limit=3, offset=3)
        assert [r[0] for r in page.rows] == [3, 4, 5]
        assert page.truncated is True
