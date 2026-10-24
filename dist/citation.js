const copyButton = document.getElementById('copy-citation');
const code = document.getElementById('citation-code');
const status = document.getElementById('copy-status');
if (copyButton && code && status) {
  copyButton.hidden = false;
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code.textContent);
      status.textContent = 'BibTeX copied.';
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(code);
      selection.removeAllRanges();
      selection.addRange(range);
      code.focus();
      status.textContent = 'Copy is unavailable. The citation is selected; press Ctrl+C or ⌘C, or download the .bib file.';
    }
  });
}
