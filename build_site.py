"""Build a dependency-free, multi-paper GitHub Pages preview."""
from pathlib import Path
import hashlib
import html
import json
import re

ROOT = Path(__file__).resolve().parent
SITE_URL = 'https://yurunsheng1.github.io/auto-beamscientist/'

def project_bibtex():
    """Cite the project website without implying a journal publication."""
    return ('@misc{autobeamscientist2026,\n'
            '  author = {{Auto BeamScientist Project}},\n'
            '  title = {{Auto BeamScientist}: Toward Autonomous Scientific Discovery in Structured Light},\n'
            '  year = {2026},\n'
            '  howpublished = {Project website},\n'
            f'  url = {{{SITE_URL}}},\n'
            '  note = {Research prototype for autonomous research in structured optics}\n'
            '}\n')

def bibtex(paper):
    """Cite the supplied report as an unpublished web resource, not a journal paper."""
    def tex(value):
        escapes={'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}',
                 '&': r'\&', '%': r'\%', '#': r'\#', '_': r'\_'}
        return ''.join(escapes.get(char,char) for char in str(value))
    key=f"autobeamscientist{paper['year']}{paper['id'].replace('-','')}"
    fields=[('author','{'+tex(paper['authors'])+'}'),
            ('title',tex(paper['title'])),('year',str(paper['year'])),
            ('howpublished','Auto BeamScientist autonomous research report'),
            ('url',SITE_URL+paper['pdf']),
            ('note','Simulation study. Peer review and novelty have not been established.')]
    return '@misc{'+key+',\n'+',\n'.join('  '+name+' = {'+value+'}' for name,value in fields)+'\n}\n'

def load_papers(path=None):
    papers=json.loads((path or ROOT/'data/papers.json').read_text())
    if not isinstance(papers,list): raise ValueError('papers.json must contain a list')
    ids=set()
    for paper in papers:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',paper['id']) or paper['id'] in ids:
            raise ValueError('Paper IDs must be unique URL-safe slugs')
        ids.add(paper['id'])
        for key in ('pdf','preview'):
            asset=ROOT/'dist'/paper[key]
            if not asset.resolve().is_relative_to((ROOT/'dist/assets').resolve()) or not asset.is_file():
                raise ValueError(f'Missing or unsafe {key} asset')
        pdf=(ROOT/'dist'/paper['pdf']).read_bytes()
        if not pdf.startswith(b'%PDF-') or hashlib.sha256(pdf).hexdigest()!=paper['sha256']:
            raise ValueError('PDF fingerprint mismatch')
        if 'code' in paper:
            asset=ROOT/'dist'/paper['code']
            if not asset.resolve().is_relative_to((ROOT/'dist/assets').resolve()) or not asset.is_file():
                raise ValueError('Missing or unsafe code bundle')
            bundle=asset.read_bytes()
            if not bundle.startswith(b'PK\x03\x04') or hashlib.sha256(bundle).hexdigest()!=paper.get('code_sha256'):
                raise ValueError('Code bundle fingerprint mismatch')
    return papers

def build():
    papers=load_papers()
    esc=html.escape
    cards=[]
    citations=ROOT/'dist/citations'
    citations.mkdir(exist_ok=True)
    (citations/'auto-beamscientist.bib').write_text(project_bibtex())
    project_page=(ROOT/'project-citation-template.html').read_text()
    (citations/'auto-beamscientist.html').write_text(
        project_page.replace('{{BIBTEX}}',esc(project_bibtex())))
    for index,p in enumerate(papers,1):
        citation_path=f"citations/{p['id']}.bib"
        (ROOT/'dist'/citation_path).write_text(bibtex(p))
        citation_page=f"citations/{p['id']}.html"
        citation_html=(ROOT/'citation-template.html').read_text()
        for token,value in {'TITLE':p['title'],'BIBTEX':bibtex(p),
                            'ID':p['id'],'PDF':p['pdf']}.items():
            citation_html=citation_html.replace('{{'+token+'}}',esc(value))
        (ROOT/'dist'/citation_page).write_text(citation_html)
        code_button=(f'<a class="download" href="{esc(p["code"])}" download="paper_01_runtime_code.zip" aria-label="Download runnable code for: {esc(p["title"])}">Runnable code <span aria-hidden="true">↓</span></a>' if p.get('code') else '')
        cards.append(f'''<article class="paper" id="{esc(p['id'])}" data-search="{esc((p['title']+' '+p['topic']).lower(),quote=True)}">
<div class="paper-no">{index:02d}</div><div class="paper-main"><p class="paper-meta">{p['year']} <span>·</span> {esc(p['topic'])} <span>·</span> {esc(p['status'])}</p>
<h3><a href="{esc(p['pdf'])}" target="_blank" rel="noopener">{esc(p['title'])}</a></h3>
<p class="paper-summary">{esc(p['summary'])}</p><p class="paper-author">{esc(p['authors'])}</p></div>
<div class="paper-actions"><a class="pdf-button" href="{esc(p['pdf'])}" target="_blank" rel="noopener" aria-label="Read PDF: {esc(p['title'])}">Read PDF <span aria-hidden="true">↗</span></a><a class="download" href="{esc(p['pdf'])}" download="{esc(p['id'])}.pdf" aria-label="Download PDF: {esc(p['title'])}">Download <span aria-hidden="true">↓</span></a><a class="download" href="{esc(citation_page)}" aria-label="View BibTeX citation: {esc(p['title'])}">BibTeX <span aria-hidden="true">→</span></a>{code_button}</div></article>''')
    template=(ROOT/'template.html').read_text()
    output=template.replace('<!-- PAPERS -->','\n'.join(cards)).replace('{{PAPER_COUNT}}',str(len(papers))).replace('{{PAPER_LABEL}}','report' if len(papers)==1 else 'reports')
    (ROOT/'dist/index.html').write_text(output)
    (ROOT/'dist/.nojekyll').touch()
    print(f'Built WIP homepage with {len(papers)} manuscripts')

if __name__=='__main__': build()
