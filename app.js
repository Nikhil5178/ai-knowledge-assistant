const fileInput = document.getElementById('file-input');
const dropzone = document.getElementById('dropzone');
const uploadStatus = document.getElementById('upload-status');
const documentList = document.getElementById('document-list');
const docCount = document.getElementById('doc-count');
const chatArea = document.getElementById('chat-area');
const questionForm = document.getElementById('question-form');
const questionInput = document.getElementById('question-input');
const askBtn = document.getElementById('ask-btn');

function setStatus(message, error = false) {
  uploadStatus.textContent = message;
  uploadStatus.classList.toggle('error', error);
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
async function refreshDocuments() {
  try {
    const res = await fetch('/api/documents');
    const data = await res.json();
    docCount.textContent = data.documents.length;
    if (!data.documents.length) {
      documentList.innerHTML = '<p class="muted small">Your uploaded files will appear here.</p>';
      return;
    }
    documentList.innerHTML = data.documents.map(d => `<div class="doc-item"><span class="doc-file">▤</span><div>${escapeHtml(d.filename)}<div class="muted small">${d.chunks} searchable chunks</div></div></div>`).join('');
  } catch (_) { /* health endpoint can be checked separately */ }
}
async function uploadFile(file) {
  if (!file) return;
  setStatus(`Uploading and indexing ${file.name}…`);
  const body = new FormData(); body.append('file', file);
  try {
    const res = await fetch('/api/upload', {method:'POST', body});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed.');
    setStatus(data.message);
    await refreshDocuments();
  } catch (err) { setStatus(err.message || 'Upload failed.', true); }
  fileInput.value = '';
}
fileInput.addEventListener('change', () => uploadFile(fileInput.files[0]));
['dragenter','dragover'].forEach(evt => dropzone.addEventListener(evt, e => {e.preventDefault();dropzone.classList.add('dragging');}));
['dragleave','drop'].forEach(evt => dropzone.addEventListener(evt, e => {e.preventDefault();dropzone.classList.remove('dragging');}));
dropzone.addEventListener('drop', e => uploadFile(e.dataTransfer.files[0]));

document.getElementById('clear-btn').addEventListener('click', async () => {
  if (!confirm('Clear all uploaded documents from this session?')) return;
  try {
    const res = await fetch('/api/documents', {method:'DELETE'});
    const data = await res.json(); setStatus(data.message); await refreshDocuments();
  } catch (_) { setStatus('Could not clear documents.', true); }
});
function appendMessage(text, role, sources = []) {
  const row = document.createElement('div'); row.className = role === 'user' ? 'user-message' : 'assistant-message';
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  const p = document.createElement('p'); p.textContent = text; bubble.appendChild(p);
  if (sources.length) {
    const details = document.createElement('details'); details.className = 'sources';
    const summary = document.createElement('summary'); summary.textContent = `Sources used (${sources.length})`; details.appendChild(summary);
    sources.forEach(s => { const div = document.createElement('div'); div.className = 'source'; div.innerHTML = `<strong>${escapeHtml(s.filename)} · chunk ${s.chunk_id}</strong><em>Similarity: ${s.score}</em>${escapeHtml(s.preview)}`; details.appendChild(div); });
    bubble.appendChild(details);
  }
  if (role !== 'user') { const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.textContent = '✦'; row.appendChild(avatar); }
  row.appendChild(bubble); chatArea.appendChild(row); chatArea.scrollTop = chatArea.scrollHeight;
}
async function askQuestion(question) {
  if (!question.trim()) return;
  document.querySelector('.suggestions')?.remove();
  appendMessage(question, 'user'); questionInput.value = ''; askBtn.disabled = true;
  const waiting = document.createElement('div'); waiting.className = 'assistant-message'; waiting.id = 'waiting'; waiting.innerHTML = '<div class="avatar">✦</div><div class="bubble"><p>Searching your documents and preparing an answer…</p></div>'; chatArea.appendChild(waiting); chatArea.scrollTop = chatArea.scrollHeight;
  try {
    const res = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question})});
    const data = await res.json(); document.getElementById('waiting')?.remove();
    if (!res.ok) throw new Error(data.detail || 'Something went wrong.');
    appendMessage(data.answer, 'assistant', data.sources || []);
  } catch (err) { document.getElementById('waiting')?.remove(); appendMessage(`Sorry — ${err.message}`, 'assistant'); }
  finally { askBtn.disabled = false; questionInput.focus(); }
}
questionForm.addEventListener('submit', e => {e.preventDefault(); askQuestion(questionInput.value);});
document.querySelectorAll('.suggestions button').forEach(button => button.addEventListener('click', () => {questionInput.value = button.textContent; questionInput.focus();}));
refreshDocuments();
