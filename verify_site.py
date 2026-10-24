"""Verify the static homepage and exact manuscript copy without dependencies."""
from pathlib import Path
from html.parser import HTMLParser
import hashlib

ROOT = Path(__file__).resolve().parent
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.refs=[]; self.ids=set()
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if 'id' in data: self.ids.add(data['id'])
        for key in ('href', 'src'):
            if key in data: self.refs.append(data[key])

def verify():
    content=(ROOT/'dist/index.html').read_text()
    parser=Links(); parser.feed(content)
    for ref in parser.refs:
        if ref.startswith('#'):
            assert ref=='#' or ref[1:] in parser.ids, ref
        elif not ref.startswith(('https:', 'http:', 'data:')):
            assert (ROOT/'dist'/ref).is_file(), ref
    for marker in ('AI for', 'better optics.', 'SIMULATION_ONLY', 'NOVELTY_NOT_VERIFIED', 'NOT_PUBLICATION_READY', 'Peer review not established'):
        assert marker in content, marker
    pdf=ROOT/'dist/assets/beam-scientist-paper.pdf'
    assert pdf.read_bytes().startswith(b'%PDF-')
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()=='15000675aa066b30fa4fa3c306aa5740b6479c6e529ea0d371b41b26224f9c08'
    print('PASS: local links, anchor targets, research status and manuscript SHA-256')

if __name__=='__main__': verify()
