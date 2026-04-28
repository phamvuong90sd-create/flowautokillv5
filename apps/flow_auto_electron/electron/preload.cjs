const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('flowAPI', {
  openFile: (opts) => ipcRenderer.invoke('dialog:openFile', opts),
  openPath: (p) => ipcRenderer.invoke('shell:openPath', p),
  status: () => ipcRenderer.invoke('flow:status'),
  ensureCdp: () => ipcRenderer.invoke('flow:ensureCdp'),
  start: (payload) => ipcRenderer.invoke('flow:start', payload),
  pause: () => ipcRenderer.invoke('flow:pause'),
  resume: () => ipcRenderer.invoke('flow:resume'),
  stop: () => ipcRenderer.invoke('flow:stop'),
  licenseCheck: () => ipcRenderer.invoke('license:check'),
  generatePrompt: (payload) => ipcRenderer.invoke('prompt:generate', payload),
  generateScript: (payload) => ipcRenderer.invoke('prompt:script', payload),
});
