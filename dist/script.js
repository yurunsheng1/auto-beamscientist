// Abstract light artwork, not simulation data.
const rays = document.getElementById('light-rays');
if (rays) {
  for (let i = 0; i < 49; i++) {
    const o = (i - 24) * 7.4;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M -20 ${240 + o} C 150 ${240 + o}, 207 ${240 - o * .1}, 280 240 S 425 ${240 - o}, 580 ${240 - o}`);
    path.setAttribute('stroke', 'url(#beam-color)');
    path.setAttribute('stroke-width', i % 4 === 0 ? '1.1' : '.65');
    path.setAttribute('fill', 'none');
    rays.appendChild(path);
  }
}
const search = document.getElementById('paper-search');
if (search) {
  const papers = [...document.querySelectorAll('article.paper')];
  const result = document.getElementById('search-result');
  search.addEventListener('input', () => {
    const term = search.value.trim().toLowerCase();
    let count = 0;
    papers.forEach(paper => {
      paper.hidden = !paper.dataset.search.includes(term);
      if (!paper.hidden) count++;
    });
    result.hidden = !term;
    result.textContent = count ? `${count} manuscript${count === 1 ? '' : 's'} found.` : 'No matching manuscripts. Try a different title or topic.';
  });
}
