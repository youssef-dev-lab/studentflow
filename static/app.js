/* Progressive enhancement only: Flask renders the UI and owns all business logic. */
document.addEventListener('input', (event) => {
  const form = event.target.closest('form[id]');
  if (form) form.dataset.dirty = 'true';
});

let saving = false;
document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!form.matches('form[data-enhance]') || !window.fetch) return;
  event.preventDefault();
  if (saving) return;
  saving = true;
  const buttons = [...form.querySelectorAll('button')];
  const body = new FormData(form);
  // Keep unrelated drafts when completing a task or adding a course.
  const drafts = [...document.querySelectorAll('form[id][data-dirty="true"]')]
    .filter((other) => other !== form)
    .map((other) => ({
      id: other.id, action: other.action, node: other, values: [...new FormData(other)],
      headingId: other.id === 'task-form' ? 'capture-title' : 'course-form-title',
      heading: document.getElementById(other.id === 'task-form' ? 'capture-title' : 'course-form-title')?.textContent,
    }));
  buttons.forEach((button) => { button.disabled = true; });
  form.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(form.action, { method: 'POST', body });
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const shell = html.getElementById('app-shell');
    if (!shell || response.status >= 500) throw new Error('Save could not be confirmed');
    document.getElementById('app-shell').replaceChildren(...shell.childNodes);
    for (const draft of drafts) {
      let other = document.getElementById(draft.id);
      if (!other) continue;
      if (other.action !== draft.action) {
        other.replaceWith(draft.node);
        other = draft.node;
        const heading = document.getElementById(draft.headingId);
        if (heading && draft.heading) heading.textContent = draft.heading;
      }
      for (const [name, value] of draft.values) {
        const field = other.elements.namedItem(name);
        if (field && typeof value === 'string') field.value = value;
      }
      other.dataset.dirty = 'true';
    }
    // Failed POST pages are not navigable GET locations; keep the existing URL.
    if (response.ok) history.replaceState(null, '', response.url);
    const feedback = document.querySelector('[role="alert"].error, [role="status"].success');
    if (feedback) feedback.focus({ preventScroll: response.ok });
    document.getElementById('network-feedback').textContent = '';
  } catch (_) {
    const feedback = document.getElementById('network-feedback');
    feedback.className = 'error network-feedback';
    feedback.textContent = 'Could not confirm the save. Reload to check your saved work before trying again.';
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
    form.removeAttribute('aria-busy');
    saving = false;
  }
});
