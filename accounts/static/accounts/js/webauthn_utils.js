// Convertit base64url → ArrayBuffer
function b64urlToBuffer(b64url) {
    const pad = b64url.length % 4 === 0 ? '' : '='.repeat(4 - b64url.length % 4);
    const b64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
}

// Convertit ArrayBuffer → base64url
function bufferToB64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer)))
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}