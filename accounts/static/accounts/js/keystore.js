/**
 * keystore.js — Secure storage of the RSA private key in IndexedDB.
 *
 * The private key is stored as a non-extractable CryptoKey (extractable=false)
 * in IndexedDB. A flag in sessionStorage indicates that the session is active.
 * If the flag is not present on load (tab closed then reopened), the key is
 * removed from IndexedDB (automatic cleanup).
 */
(function (global) {
    'use strict';

    const DB_NAME    = 'e2e_keystore';
    const DB_VERSION = 1;
    const STORE_NAME = 'keys';
    const KEY_ID     = 'privateKey';
    const SESSION_FLAG = 'ks_session_active';

    // ── Opening / creating the database ───────────────────────────────────────

    function openDB() {
        return new Promise(function (resolve, reject) {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                e.target.result.createObjectStore(STORE_NAME);
            };
            req.onsuccess = function (e) { resolve(e.target.result); };
            req.onerror   = function (e) { reject(e.target.error); };
        });
    }

    // ── Public API ───────────────────────────────────────────────────────────

    /**
     * Stores a non-extractable CryptoKey object in IndexedDB and sets the
     * session flag in sessionStorage.
     *
     * @param {CryptoKey} cryptoKey  RSA-OAEP private key (extractable=false, usage=['decrypt'])
     */
    async function storePrivateKey(cryptoKey) {
        const db = await openDB();
        await new Promise(function (resolve, reject) {
            const tx  = db.transaction(STORE_NAME, 'readwrite');
            const req = tx.objectStore(STORE_NAME).put(cryptoKey, KEY_ID);
            req.onsuccess = resolve;
            req.onerror   = function (e) { reject(e.target.error); };
        });
        sessionStorage.setItem(SESSION_FLAG, '1');
    }

    /**
     * Returns the stored CryptoKey, or null if it is not available.
     */
    async function getPrivateKey() {
        const db = await openDB();
        return new Promise(function (resolve, reject) {
            const tx  = db.transaction(STORE_NAME, 'readonly');
            const req = tx.objectStore(STORE_NAME).get(KEY_ID);
            req.onsuccess = function (e) { resolve(e.target.result || null); };
            req.onerror   = function (e) { reject(e.target.error); };
        });
    }

    /**
     * Deletes the key from IndexedDB and clears the session flag.
     */
    async function clearKeys() {
        const db = await openDB();
        await new Promise(function (resolve, reject) {
            const tx  = db.transaction(STORE_NAME, 'readwrite');
            const req = tx.objectStore(STORE_NAME).delete(KEY_ID);
            req.onsuccess = resolve;
            req.onerror   = function (e) { reject(e.target.error); };
        });
        sessionStorage.removeItem(SESSION_FLAG);
    }

    /**
     * Indicates whether a key is available (session flag present AND key in store).
     * Should be called asynchronously for a full check.
     */
    async function isKeyAvailable() {
        if (!sessionStorage.getItem(SESSION_FLAG)) return false;
        const key = await getPrivateKey();
        return key !== null;
    }

    // ── Cleanup on load ────────────────────────────────────────────────────────
    // If the sessionStorage flag is absent (tab closed / fresh start), purge
    // IndexedDB to avoid an orphaned key.
    (async function cleanupOnLoad() {
        if (!sessionStorage.getItem(SESSION_FLAG)) {
            try { await clearKeys(); } catch (_) {}
        }
    })();

    // ── Global export ────────────────────────────────────────────────────────
    global.KeyStore = {
        storePrivateKey : storePrivateKey,
        getPrivateKey   : getPrivateKey,
        clearKeys       : clearKeys,
        isKeyAvailable  : isKeyAvailable,
    };

})(window);
