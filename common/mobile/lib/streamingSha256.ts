const K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

/**
 * Pure-JS Streaming SHA-256 Hasher.
 * Allows hashing arbitrarily large files incrementally in small chunks without
 * memory allocation spikes or OOM errors on mobile engines (Hermes/JSC).
 */
export class StreamingSha256 {
  private h0 = 0x6a09e667;
  private h1 = 0xbb67ae85;
  private h2 = 0x3c6ef372;
  private h3 = 0xa54ff53a;
  private h4 = 0x510e527f;
  private h5 = 0x9b05688c;
  private h6 = 0x1f83d9ab;
  private h7 = 0x5be0cd19;

  private buffer = new Uint8Array(64);
  private bufferLength = 0;
  private totalBytes = 0;
  private w = new Uint32Array(64);

  private compress(block: Uint8Array, offset: number) {
    const view = new DataView(block.buffer, block.byteOffset + offset, 64);
    const w = this.w;
    for (let t = 0; t < 16; t++) {
      w[t] = view.getUint32(t * 4, false);
    }
    const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (((w[t - 16] + s0) >>> 0) + ((w[t - 7] + s1) >>> 0)) >>> 0;
    }

    let a = this.h0, b = this.h1, c = this.h2, d = this.h3;
    let e = this.h4, f = this.h5, g = this.h6, h = this.h7;

    for (let t = 0; t < 64; t++) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ ((~e) & g);
      const temp1 = (((h + s1) >>> 0) + (((ch + K[t]) >>> 0) + w[t]) >>> 0) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    this.h0 = (this.h0 + a) >>> 0;
    this.h1 = (this.h1 + b) >>> 0;
    this.h2 = (this.h2 + c) >>> 0;
    this.h3 = (this.h3 + d) >>> 0;
    this.h4 = (this.h4 + e) >>> 0;
    this.h5 = (this.h5 + f) >>> 0;
    this.h6 = (this.h6 + g) >>> 0;
    this.h7 = (this.h7 + h) >>> 0;
  }

  update(chunk: Uint8Array): this {
    let offset = 0;
    let length = chunk.length;
    this.totalBytes += length;

    if (this.bufferLength > 0) {
      const needed = 64 - this.bufferLength;
      if (length >= needed) {
        this.buffer.set(chunk.subarray(0, needed), this.bufferLength);
        this.compress(this.buffer, 0);
        offset += needed;
        length -= needed;
        this.bufferLength = 0;
      } else {
        this.buffer.set(chunk, this.bufferLength);
        this.bufferLength += length;
        return this;
      }
    }

    while (length >= 64) {
      this.compress(chunk, offset);
      offset += 64;
      length -= 64;
    }

    if (length > 0) {
      this.buffer.set(chunk.subarray(offset, offset + length), 0);
      this.bufferLength = length;
    }

    return this;
  }

  digest(): string {
    const totalBytes = this.totalBytes;
    const bitLenHi = Math.floor(totalBytes / 0x20000000);
    const bitLenLo = (totalBytes * 8) >>> 0;

    const padLen = (totalBytes % 64 < 56) ? (56 - (totalBytes % 64)) : (120 - (totalBytes % 64));
    const padding = new Uint8Array(padLen + 8);
    padding[0] = 0x80;
    const view = new DataView(padding.buffer, padding.byteOffset, padding.byteLength);
    view.setUint32(padLen, bitLenHi, false);
    view.setUint32(padLen + 4, bitLenLo, false);

    let padOffset = 0;
    let padLength = padding.length;
    if (this.bufferLength > 0) {
      const needed = 64 - this.bufferLength;
      this.buffer.set(padding.subarray(0, needed), this.bufferLength);
      this.compress(this.buffer, 0);
      padOffset += needed;
      padLength -= needed;
      this.bufferLength = 0;
    }
    while (padLength >= 64) {
      this.compress(padding, padOffset);
      padOffset += 64;
      padLength -= 64;
    }

    const toHex = (n: number) => (n >>> 0).toString(16).padStart(8, '0');
    return (
      toHex(this.h0) + toHex(this.h1) + toHex(this.h2) + toHex(this.h3) +
      toHex(this.h4) + toHex(this.h5) + toHex(this.h6) + toHex(this.h7)
    );
  }
}
