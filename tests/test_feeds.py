from intelligent_investor.feeds import parse_feed


def test_parse_rss_and_atom_links() -> None:
    rss = b"""<rss><channel><item><title>Quarterly results</title>
        <link>https://example.com/results</link><guid>r1</guid>
        <pubDate>today</pubDate></item></channel></rss>"""
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Annual report</title><link href="https://example.com/annual"/>
        <id>a1</id><updated>today</updated></entry></feed>"""

    assert list(parse_feed(rss))[0]["url"] == "https://example.com/results"
    assert list(parse_feed(atom))[0]["url"] == "https://example.com/annual"
