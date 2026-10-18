"""Số đếm actor dạng chữ ("5.4K") không được làm hỏng bước cào bình luận (18/10/2026).

Lượt 16 (18/10/2026): actor bình luận Facebook trả `likesCount` = "5.4K", `int()` ném ValueError
và cả bước bình luận của lượt hỏng — Threads/Facebook không được cào dòng nào."""
import pytest

import deep_dive_tool as D


@pytest.mark.parametrize("v, ra", [
    (12, 12), (12.7, 12), ("12", 12), ("1,234", 1234), ("1.234", 1234), ("5.4K", 5400),
    ("5,4k", 5400), ("1,2M", 1_200_000), ("2B", 2_000_000_000), (" 7 ", 7), ("", 0),
    (None, 0), ("abc", 0), ("K", 0), (-3, 0), (True, 1),
])
def test_so_doc_duoc_so_dem_dang_chu(v, ra):
    assert D._so(v) == ra


def test_map_facebook_nhan_like_dang_chu():
    rows, n = D._map_facebook([{"text": "Túi đẹp quá", "profileName": "A", "likesCount": "5.4K",
                                "replyCount": "1,2K", "facebookUrl": "https://www.facebook.com/x/posts/1"}])
    assert n == 1 and rows[0]["likes"] == 5400 and rows[0]["replies"] == 1200


def test_map_tiktok_va_youtube_khong_vo_khi_so_la():
    tt, _ = D._map_tiktok([{"cid": "1", "text": "ok", "diggCount": "3K", "replyCommentTotal": "x"}])
    yt, _ = D._map_youtube([{"comment": "hay", "voteCount": "1.5K", "replyCount": None}])
    assert tt[0]["likes"] == 3000 and tt[0]["replies"] == 0
    assert yt[0]["likes"] == 1500 and yt[0]["replies"] == 0
