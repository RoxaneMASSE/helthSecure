/**
 * keystore.js — Gestion sécurisée de la clé privée RSA dans IndexedDB.
 *
 * La clé privée est stockée comme CryptoKey non-extractable (extractable=false)
 * dans IndexedDB. Un flag dans sessionStorage indique que la session est active.
 * Si le flag n'est pas présent au chargement (onglet fermé puis rouvert), la
 * clé est supprimée d'IndexedDB (nettoyage automatique).
 */
(function (global) {
    'use strict';

    const DB_NAME    = 'e2e_keystore';
    const DB_VERSION = 1;
    const STORE_NAME = 'keys';
    const KEY_ID     = 'privateKey';
    const SESSION_FLAG = 'ks_session_active';

    // ── Ouverture / création de la base ──────────────────────────────────────

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

    // ── API publique ──────────────────────────────────────────────────────────

    /**
     * Stocke un objet CryptoKey non-extractable dans IndexedDB et pose le flag
     * de session dans sessionStorage.
     *
     * @param {CryptoKey} cryptoKey  Clé privée RSA-OAEP (extractable=false, usage=['decrypt'])
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
     * Retourne la CryptoKey stockée, ou null si elle n'est pas disponible.
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
     * Supprime la clé d'IndexedDB et retire le flag de session.
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
     * Indique si une clé est disponible (flag session présent ET clé en base).
     * À appeler en async pour une vérification complète.
     */
    async function isKeyAvailable() {
        if (!sessionStorage.getItem(SESSION_FLAG)) return false;
        const key = await getPrivateKey();
        return key !== null;
    }

    // ── Nettoyage au chargement ───────────────────────────────────────────────
    // Si le flag sessionStorage est absent (onglet fermé/nouveau démarrage),
    // on purge IndexedDB pour éviter une clé orpheline.
    (async function cleanupOnLoad() {
        if (!sessionStorage.getItem(SESSION_FLAG)) {
            try { await clearKeys(); } catch (_) {}
        }
    })();

    // ── Export global ─────────────────────────────────────────────────────────
    global.KeyStore = {
        storePrivateKey : storePrivateKey,
        getPrivateKey   : getPrivateKey,
        clearKeys       : clearKeys,
        isKeyAvailable  : isKeyAvailable,
    };

})(window);
