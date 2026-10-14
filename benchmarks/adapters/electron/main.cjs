const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const nonce = process.env.TINYJS_BENCH_NONCE;
const marker = process.env.TINYJS_BENCH_READY;
ipcMain.handle('challenge', () => ({ nonce, values: Array.from({ length: 1000 }, (_, i) => i) }));
ipcMain.handle('finish', (_event, params) => {
  if (!nonce || !marker || params.nonce !== nonce || params.checksum !== 499500)
    throw new Error('Invalid benchmark challenge');
  fs.writeFileSync(marker, JSON.stringify(params));
  return true;
});
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 800, height: 600,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  win.loadFile(path.join(__dirname, 'frontend', 'index.html'));
});
app.on('window-all-closed', () => app.quit());
