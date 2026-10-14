// Runs in txiki.js. Each RPC handler receives (params, app).
const KEY = 'notes';
const MAX_TEXT = 2000;
let sequence = 0;

// Keep read/modify/write operations in order, even if calls overlap.
let pending = Promise.resolve();
function inOrder(operation) {
  const result = pending.then(operation);
  pending = result.catch(() => {});
  return result;
}

function textFrom(params) {
  const text = params?.text;
  if (typeof text !== 'string' || !text.trim() || text.length > MAX_TEXT) {
    throw new Error('Write a note between 1 and 2000 characters.');
  }
  return text; // Preserve whitespace and Unicode exactly as entered.
}

async function readNotes(app) {
  const notes = await app.store.get(KEY);
  if (notes === null) return [];
  if (!Array.isArray(notes) || notes.some((note) =>
    !note || typeof note.id !== 'string' || typeof note.text !== 'string')) {
    throw new Error('Stored notes have an unexpected format. Back up store.json before changing it.');
  }
  return notes;
}

async function saveNotes(app, notes) {
  // store.set resolves false on a disk error; awaiting alone is not enough.
  if (!await app.store.set(KEY, notes)) {
    throw new Error('Could not save notes to disk. Keep your text and check available space and permissions.');
  }
  return notes;
}

export const api = {
  listNotes(_params, app) {
    return inOrder(() => readNotes(app));
  },

  addNote(params, app) {
    return inOrder(async () => {
      const text = textFrom(params);
      const notes = await readNotes(app);
      let id;
      do {
        id = Date.now().toString(36) + '-' + (++sequence);
      } while (notes.some((note) => note.id === id));
      return saveNotes(app, [...notes, { id, text }]);
    });
  },

  updateNote(params, app) {
    return inOrder(async () => {
      const text = textFrom(params);
      const notes = await readNotes(app);
      if (!notes.some((note) => note.id === params.id)) throw new Error('Note no longer exists.');
      return saveNotes(app, notes.map((note) => note.id === params.id ? { ...note, text } : note));
    });
  },

  deleteNote(params, app) {
    return inOrder(async () => {
      const notes = await readNotes(app);
      if (!notes.some((note) => note.id === params?.id)) throw new Error('Note no longer exists.');
      return saveNotes(app, notes.filter((note) => note.id !== params.id));
    });
  },
};
