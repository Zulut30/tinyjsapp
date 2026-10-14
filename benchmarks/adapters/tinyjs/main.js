const nonce = tjs.env.TINYJS_BENCH_NONCE;
const marker = tjs.env.TINYJS_BENCH_READY;
export const api = {
  challenge() { return { nonce, values: Array.from({ length: 1000 }, (_, i) => i) }; },
  async finish(params) {
    if (!nonce || !marker || params.nonce !== nonce || params.checksum !== 499500)
      throw new Error('Invalid benchmark challenge');
    await tjs.writeFile(marker, new TextEncoder().encode(JSON.stringify(params)));
    return true;
  },
};
