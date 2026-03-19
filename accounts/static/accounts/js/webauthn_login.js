document.addEventListener('DOMContentLoaded', () => {

    function showError(msg) {
        const box = document.getElementById('error-box');
        box.textContent = msg;
        box.style.display = 'block';
    }

    document.getElementById('btn-webauthn').addEventListener('click', async () => {
        const username = document.getElementById('username').value.trim();
        if (!username) { showError('Please enter your email.'); return; }

        try {
            const beginResp = await fetch(WEBAUTHN_LOGIN_BEGIN_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify({ username }),
            });

            if (!beginResp.ok) {
                const err = await beginResp.json();
                showError(err.error || 'Authentication failed.');
                return;
            }

            const options = await beginResp.json();
            options.challenge = b64urlToBuffer(options.challenge);
            options.allowCredentials = (options.allowCredentials || []).map(c => ({
                ...c,
                id: b64urlToBuffer(c.id),
            }));

            const assertion = await navigator.credentials.get({ publicKey: options });

            const credential = {
                id: assertion.id,
                rawId: bufferToB64url(assertion.rawId),
                type: assertion.type,
                response: {
                    authenticatorData: bufferToB64url(assertion.response.authenticatorData),
                    clientDataJSON:    bufferToB64url(assertion.response.clientDataJSON),
                    signature:         bufferToB64url(assertion.response.signature),
                    userHandle: assertion.response.userHandle
                        ? bufferToB64url(assertion.response.userHandle)
                        : null,
                },
            };

            const completeResp = await fetch(WEBAUTHN_LOGIN_COMPLETE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify(credential),
            });

            const result = await completeResp.json();
            if (result.status === 'ok') {
                window.location.href = result.redirect;
            } else {
                showError(result.error || 'Authentication failed.');
            }

        } catch (err) {
            showError(err.name === 'NotAllowedError'
                ? 'Authentication cancelled or timed out.'
                : 'WebAuthn error: ' + err.message);
        }
    });

});