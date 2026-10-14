// Identical frontend in all three packaged apps. Adapter only supplies IPC.
(async () => {
  // tinyjs injects its client asynchronously; use the same bounded polling everywhere.
  const deadline = performance.now() + 10000;
  while (!window.benchmark && !window.tiny?.api && !window.__TAURI__?.core) {
    if (performance.now() > deadline) throw new Error('IPC client unavailable');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  const call = window.benchmark?.call
    || (window.tiny ? (name, params) => tiny.api.call(name, params)
      : (name, params) => window.__TAURI__.core.invoke(name, params));
  const { nonce, values } = await call('challenge');
  let checksum = 0;
  const fragment = document.createDocumentFragment();
  for (const value of values) {
    checksum += value;
    const row = document.createElement('div');
    row.textContent = String(value);
    fragment.appendChild(row);
  }
  document.getElementById('rows').appendChild(fragment);
  document.querySelector('output').textContent = String(checksum);
  if (document.getElementById('rows').getBoundingClientRect().height <= 0)
    throw new Error('Workload layout unavailable');
  // This is a readiness proxy, not a compositor/pixel presentation timestamp.
  await call('finish', { nonce, checksum });
})().catch(error => { document.querySelector('output').textContent = error.message; });
