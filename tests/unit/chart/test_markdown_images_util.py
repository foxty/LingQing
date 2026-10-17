"""Tests for shared markdown image parsing."""

from apps.shared.utils.markdown_images import iter_markdown_image_tuples


def test_iter_markdown_image_tuples_preserves_order():
    md = "![A](http://a/1.png)\n\n![B](http://b/2.svg)"
    assert iter_markdown_image_tuples(md) == [
        ("A", "http://a/1.png"),
        ("B", "http://b/2.svg"),
    ]
