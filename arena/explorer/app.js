const $ = id => document.getElementById(id);
const state = {offset: 0, limit: 20, total: 0, selected: null, generation: 0, detailGeneration: 0};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dataset = () => $('dataset').value;
async function get(url) { const r = await fetch(url); if (!r.ok) throw new Error(`Request failed (${r.status})`); return r.json(); }
function resetDetail() { state.selected = null; state.detailGeneration++; $('detail').innerHTML = '<div class="empty">Select a conversation to view the prompt and responses.</div>'; }
const fmt = n => Number(n).toLocaleString();
const REASONS = {short_win: 'Shorter answer won', tie: 'Tie', both_bad: 'Both bad', near_equal_win: 'Longer answer won by <5%'};
const lengthNote = r => {
  if (!r.inclusion_reason) return '';
  const lengths = r.winner_chars != null ? `${fmt(r.winner_chars)} vs ${fmt(r.loser_chars)} chars` : `A ${fmt(r.answer_a_chars)} · B ${fmt(r.answer_b_chars)} chars`;
  return `<span class="result-length">${REASONS[r.inclusion_reason]} · ${lengths} (${r.length_diff_pct}% diff)</span>`;
};
const winnerTag = (r, side) => r.winner === side ? ' <span class="win-tag">Winner</span>' : '';
const charTag = n => n != null ? `<div class="char-count">${fmt(n)} chars</div>` : '';
async function search() {
  const generation = ++state.generation;
  const ds = dataset();
  const notices = {
    french: 'French shortlist: searches available text and metadata. Text is shown when the local enriched CSV has been generated from the authorized source.',
    short_wins: 'Short answer wins, tie or both bad: Arena ranked-shortlist votes where the shorter answer won, the vote was a tie or both_bad, or the longer answer won by less than 5% in length. Excludes only wins by an answer ≥5% longer. Length = characters in each final answer. Filter by reason with reason:short_win, reason:tie, reason:both_bad or reason:near_equal_win.',
  };
  $('notice').textContent = notices[ds] || 'Search covers the full prompt, all user turns, both model outputs, model names and conversation ID.';
  $('results').innerHTML = '<div class="empty">Loading conversations…</div>';
  try {
    const params = new URLSearchParams({dataset: ds, q: $('search').value, offset: state.offset, limit: state.limit});
    const data = await get('/api/query?' + params);
    if (generation !== state.generation) return;
    state.total = data.total;
    $('count').textContent = `${data.total.toLocaleString()} found`;
    $('results').innerHTML = data.rows.length ? data.rows.map(r => `<button class="result ${r.id === state.selected ? 'selected' : ''}" data-id="${esc(r.id)}"><span class="result-prompt">${esc(r.prompt || r.source_primary_topic || 'Conversation metadata')}</span><span class="result-meta">${esc(r.model_a || 'Unknown model')} <span class="vs">vs</span> ${esc(r.model_b || 'Unknown model')}</span>${lengthNote(r)}<span class="result-id">${esc(r.id)}</span></button>`).join('') : '<div class="empty">No conversations match these keywords.</div>';
    $('page').textContent = data.total ? `${state.offset + 1}–${Math.min(state.offset + state.limit, data.total)} of ${data.total.toLocaleString()}` : '0 results';
    $('prev').disabled = state.offset === 0; $('next').disabled = state.offset + state.limit >= data.total;
    document.querySelectorAll('.result').forEach(button => button.addEventListener('click', () => openRow(button.dataset.id)));
  } catch (e) { if (generation === state.generation) $('results').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
async function openRow(id) {
  state.selected = id; const generation = ++state.detailGeneration; const ds = dataset();
  document.querySelectorAll('.result').forEach(b => b.classList.toggle('selected', b.dataset.id === id));
  $('detail').innerHTML = '<div class="empty">Loading conversation…</div>';
  try {
    const r = await get('/api/row?' + new URLSearchParams({dataset: ds, id}));
    if (generation !== state.detailGeneration) return;
    const missing = 'Full text is unavailable for this record.';
    const turns = r.user_turns && r.user_turns.length ? r.user_turns : (r.prompt ? [r.prompt] : []);
    const prompt = turns.length ? turns.map((t,i) => `<div class="turn">${turns.length > 1 ? `<div class="turn-label">User turn ${i+1}</div>` : ''}<div class="text">${esc(t)}</div></div>`).join('') : `<div class="unavailable">${missing}</div>`;
    const answer = (text, turns) => turns && turns.length ? turns.map((t,i) => `<div class="turn">${turns.length > 1 ? `<div class="turn-label">Assistant turn ${i+1}</div>` : ''}<div class="text">${esc(t)}</div></div>`).join('') : text ? `<div class="text">${esc(text)}</div>` : `<div class="unavailable">${missing}</div>`;
    const differs = r.user_turns_b && JSON.stringify(r.user_turns_a) !== JSON.stringify(r.user_turns_b);
    const promptB = differs ? `<div class="turn-label">Model B user turns (different from A)</div>${r.user_turns_b.map((t,i) => `<div class="turn"><div class="turn-label">User turn ${i+1}</div><div class="text">${esc(t)}</div></div>`).join('')}` : '';
    const warning = r.text_warnings ? `<div class="notice">Text needs review: ${esc(r.text_warnings)}</div>` : '';
    $('detail').innerHTML = `<div class="detail-head"><div><div class="eyebrow">CONVERSATION</div><h2>Compare responses</h2><div class="detail-id">${esc(r.id)}</div></div><div class="badge">${esc(r.winner ? 'Vote: ' + r.winner : 'No vote')}${r.inclusion_reason ? ' · ' + REASONS[r.inclusion_reason] + ' (' + r.length_diff_pct + '% length diff)' : ''}</div></div><section class="prompt-block"><div class="section-label">USER PROMPT ${turns.length > 1 ? '· ALL TURNS' : ''}</div>${prompt}${promptB}${warning}</section><div class="answers"><section class="answer"><div class="answer-head"><div class="section-label">MODEL A${winnerTag(r, 'model_a')}</div><h3>${esc(r.model_a || 'Unknown model')}</h3>${charTag(r.answer_a_chars)}</div>${answer(r.assistant_a, r.assistant_turns_a)}</section><section class="answer"><div class="answer-head"><div class="section-label">MODEL B${winnerTag(r, 'model_b')}</div><h3>${esc(r.model_b || 'Unknown model')}</h3>${charTag(r.answer_b_chars)}</div>${answer(r.assistant_b, r.assistant_turns_b)}</section></div><div class="detail-foot">${esc(r.timestamp || '')}${r.source_primary_topic ? ' · ' + esc(r.source_primary_topic) : ''}</div>`;
  } catch(e) { if (generation === state.detailGeneration) $('detail').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
let timer;
$('search').addEventListener('input', () => { clearTimeout(timer); state.generation++; state.offset = 0; resetDetail(); timer = setTimeout(search, 250); });
$('dataset').addEventListener('change', () => { clearTimeout(timer); state.offset = 0; resetDetail(); search(); });
$('prev').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.limit); search(); });
$('next').addEventListener('click', () => { state.offset += state.limit; search(); });
search();
