const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('benchmark', {
  call(name, params) {
    if (!['challenge', 'finish'].includes(name)) throw new Error('Unknown benchmark command');
    return ipcRenderer.invoke(name, params);
  },
});
