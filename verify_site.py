"""Check generated local links, manuscript hashes, and WIP disclosures."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from build_site import load_papers
ROOT=Path(__file__).resolve().parent
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.refs=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if 'id' in data:self.ids.add(data['id'])
        for key in ('href','src'):
            if key in data:self.refs.append(data[key])
def verify():
    content=(ROOT/'dist/index.html').read_text()
    parser=Links();parser.feed(content)
    for page in (ROOT/'dist').rglob('*.html'):
        links=Links();links.feed(page.read_text())
        for ref in links.refs:
            url=urlsplit(ref)
            if url.scheme or url.netloc:continue
            target=page.parent/url.path if url.path else page
            assert target.resolve().is_relative_to((ROOT/'dist').resolve()),ref
            assert target.is_file(),ref
            if url.fragment:
                destination=Links();destination.feed(target.read_text())
                assert url.fragment in destination.ids,ref
    for marker in ('better optics.','AN AI SCIENTIST FOR STRUCTURED LIGHT','Toward Autonomous Scientific Discovery in Structured Light','Work in progress','SIMULATION_ONLY','NOVELTY_NOT_VERIFIED','NOT_PUBLICATION_READY'):
        assert marker in content,marker
    for paper in load_papers():assert paper['id'] in parser.ids,paper['id']
    assert '<!-- PAPERS -->' not in content
    print('PASS: WIP homepage, multi-paper links, asset paths and PDF fingerprints')
if __name__=='__main__':verify()
