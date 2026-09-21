const $ = (id) => document.getElementById(id);
const today = new Date();
const localDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
const form = $('expense-form');
form.elements.date.value = localDate;
$('month').value = localDate.slice(0,7);
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e => `${e.loc.at(-1)}: ${e.msg}`).join('; ') : data.detail || 'Request failed');
  return data;
}
function item(text) { const li = document.createElement('li'); li.textContent = text; return li; }
async function refresh() {
  const [summary, expenses] = await Promise.all([api(`/summary?month=${encodeURIComponent($('month').value)}`), api('/expenses')]);
  $('total').textContent = `Total spend: ${summary.total_spend}`;
  const change = summary.month_over_month_change_percent;
  $('change').textContent = change === null ? 'Month-over-month change unavailable: previous month has no spend.' : `${change > 0 ? '+' : ''}${change}% versus previous month (${summary.previous_month_total})`;
  $('categories').replaceChildren(...Object.entries(summary.spend_by_category).map(([cat, value]) => item(`${cat}: ${value}`)));
  if (!Object.keys(summary.spend_by_category).length) $('categories').append(item('No expenses this month.'));
  $('insights').replaceChildren(...summary.insights.map(i => item(`${i.category} spending increased ${i.increase_percent}% versus last month.`)));
  $('expenses').replaceChildren(...expenses.map(e => {
    const row = document.createElement('tr');
    for (const value of [e.date,e.category,e.amount,e.note]) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
    return row;
  }));
}
form.addEventListener('submit', async event => {
  event.preventDefault(); $('save').disabled = true; $('status').textContent = '';
  try {
    const payload = Object.fromEntries(new FormData(form));
    await api('/expenses', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('month').value = payload.date.slice(0,7);
    form.elements.amount.value = ''; form.elements.note.value = '';
    $('status').textContent = 'Expense saved.';
    try { await refresh(); } catch (e) { $('status').textContent = `Expense saved, but refresh failed: ${e.message}`; }
  } catch(e) { $('status').textContent = e.message; }
  finally { $('save').disabled = false; }
});
$('month').addEventListener('change', () => refresh().catch(e => $('status').textContent = e.message));
refresh().catch(e => $('status').textContent = e.message);
