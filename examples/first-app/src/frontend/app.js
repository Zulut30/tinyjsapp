const $ = (id) => document.getElementById(id);
let editing = null;
let busy = false;

function resetEditor() {
  editing = null;
  $('text').value = '';
  $('save').textContent = 'Add note';
  $('cancel').hidden = true;
}

function render(notes) {
  $('notes').replaceChildren();
  $('empty').hidden = notes.length !== 0;
  for (const note of notes) {
    const item = document.createElement('li');
    const text = document.createElement('p');
    text.textContent = note.text; // Notes are text, never HTML.
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.textContent = 'Edit';
    edit.addEventListener('click', () => {
      if (busy) return;
      editing = note.id;
      $('text').value = note.text;
      $('save').textContent = 'Save changes';
      $('cancel').hidden = false;
      $('text').focus();
    });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Delete';
    remove.addEventListener('click', () => perform(async () => {
      const notes = await tiny.api.call('deleteNote', { id: note.id });
      if (editing === note.id) resetEditor();
      render(notes);
    }, 'Note deleted.'));
    item.append(text, edit, remove);
    $('notes').append(item);
  }
}

async function perform(operation, message) {
  if (busy) return;
  busy = true;
  $('controls').disabled = true;
  for (const button of $('notes').querySelectorAll('button')) button.disabled = true;
  $('error').textContent = '';
  $('status').textContent = 'Working…';
  try {
    await operation();
    $('status').textContent = message;
  } catch (error) {
    $('error').textContent = error.message || String(error);
    $('status').textContent = 'Operation failed. Your editor text has been kept.';
  } finally {
    busy = false;
    $('controls').disabled = false;
    for (const button of $('notes').querySelectorAll('button')) button.disabled = false;
  }
}

$('editor').addEventListener('submit', (event) => {
  event.preventDefault();
  perform(async () => {
    const notes = await tiny.api.call(editing ? 'updateNote' : 'addNote', {
      id: editing,
      text: $('text').value,
    });
    render(notes);
    resetEditor();
    $('text').focus();
  }, 'Note saved.');
});
$('cancel').addEventListener('click', resetEditor);

perform(async () => render(await tiny.api.call('listNotes')), 'Ready.');
