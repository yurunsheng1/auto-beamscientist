"""Build a dependency-free, multi-paper GitHub Pages preview."""
from pathlib import Path
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from publication_records import read_records, verified_versions, REPOSITORY

ROOT = Path(__file__).resolve().parent
SITE_URL = 'https://yurunsheng1.github.io/auto-beamscientist/'

def publication_html(paper, records):
    esc=html.escape
    first,current=verified_versions(paper,records)
    def date(record):
        stamp=datetime.fromisoformat(record['published_at_utc'].replace('Z','+00:00'))
        label=stamp.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC+08:00')
        return f'<time datetime="{esc(record["published_at_utc"])}">{label}</time>'
    summary=(f'First verified public: {date(first)}' if first else 'Public-release verification pending')
    blocks=[]
    for label,record in [('Earliest verified public deployment',first),('Current PDF version',current)]:
        if record is None:
            blocks.append(f'<div class="release-version"><h3>{label}</h3><p>Verification pending for this PDF version.</p></div>')
            continue
        snapshot=f'https://github.com/{REPOSITORY}/blob/{record["commit_sha"]}/dist/{record["pdf_path"]}'
        commit=f'https://github.com/{REPOSITORY}/commit/{record["commit_sha"]}'
        blocks.append(f'<div class="release-version"><h3>{label}</h3><p>{date(record)}</p><div class="release-links"><a href="{esc(record["status_url"])}" target="_blank" rel="noopener">GitHub timestamp ↗</a><a href="{commit}" target="_blank" rel="noopener">Source commit ↗</a><a href="{esc(snapshot)}" target="_blank" rel="noopener">PDF at this commit ↗</a></div><p class="release-hash">SHA-256 <code>{record["pdf_sha256"]}</code></p></div>')
    panel='<section class="publication-record" id="publication"><p class="eyebrow">PUBLICATION RECORD</p><h2>Public release &amp; version history</h2><p class="publication-explanation">Times are taken from successful GitHub Pages deployment records, rather than editable Git commit dates. File hashes identify the exact PDFs.</p>'+''.join(blocks)+'<a class="download" href="../publication-records.json" download>Download verification receipts ↓</a><p class="publication-explanation">This records verifiable public availability on this site; it is not proof of scientific priority. GitHub may expire historical status records; the downloaded receipts preserve the responses collected during verification.</p></section>'
    return summary,panel

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
    note='Simulation study. Peer review and novelty have not been established.'
    fields=[('author','{'+tex(paper['authors'])+'}'),
            ('title',tex(paper['title'])),('year',str(paper['year'])),
            ('howpublished','Auto BeamScientist autonomous research report'),
            ('url',SITE_URL+paper['pdf']),
            ('note',note)]
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
    records=read_records()
    (ROOT/'dist/publication-records.json').write_text(json.dumps(records,indent=2)+'\n')
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
        publication_summary,publication_panel=publication_html(p,records)
        citation_html=(ROOT/'citation-template.html').read_text()
        for token,value in {'TITLE':p['title'],'BIBTEX':bibtex(p),
                            'ID':p['id'],'PDF':p['pdf']}.items():
            citation_html=citation_html.replace('{{'+token+'}}',esc(value))
        citation_html=citation_html.replace('{{PUBLICATION_RECORD}}',publication_panel)
        (ROOT/'dist'/citation_page).write_text(citation_html)
        code_button=(f'<a class="download" href="{esc(p["code"])}" download="{esc(Path(p["code"]).name)}" aria-label="Download numerical code for: {esc(p["title"])}">Code <span aria-hidden="true">↓</span></a>' if p.get('code') else '')
        cards.append(f'''<article class="paper" id="{esc(p['id'])}" data-search="{esc((p['title']+' '+p['topic']).lower(),quote=True)}">
<div class="paper-no">{index:02d}</div><div class="paper-main"><p class="paper-meta">{p['year']} <span>·</span> {esc(p['topic'])} <span>·</span> {esc(p['status'])}</p>
<h3><a href="{esc(p['pdf'])}" target="_blank" rel="noopener">{esc(p['title'])}</a></h3>
<p class="paper-summary">{esc(p['summary'])}</p><p class="paper-author">{esc(p['authors'])}</p><p class="publication-date">{publication_summary}<br><a href="{esc(citation_page)}#publication">Verify publication &amp; PDF version →</a></p></div>
<div class="paper-actions"><a class="pdf-button" href="{esc(p['pdf'])}" target="_blank" rel="noopener" aria-label="Read paper: {esc(p['title'])}">Paper <span aria-hidden="true">↗</span></a>{code_button}</div></article>''')
    template=(ROOT/'template.html').read_text()
    output=template.replace('<!-- PAPERS -->','\n'.join(cards)).replace('{{PAPER_COUNT}}',str(len(papers))).replace('{{PAPER_LABEL}}','report' if len(papers)==1 else 'reports')
    (ROOT/'dist/index.html').write_text(output)
    (ROOT/'dist/.nojekyll').touch()
    print(f'Built WIP homepage with {len(papers)} manuscripts')

if __name__=='__main__': build()
