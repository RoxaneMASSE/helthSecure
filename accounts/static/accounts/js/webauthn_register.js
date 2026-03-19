document.addEventListener('DOMContentLoaded', () => {

    document.getElementById('btn-register-webauthn').addEventListener('click', async () => {
        const status = document.getElementById('webauthn-status');
        status.textContent = 'Starting registration...';
        status.style.color = '#457b9d';

        try {
            const beginResp = await fetch(WEBAUTHN_REGISTER_BEGIN_URL);
            const options = await beginResp.json();

            options.challenge = b64urlToBuffer(options.challenge);
            options.user.id   = b64urlToBuffer(options.user.id);
            (options.excludeCredentials || []).forEach(c => {
                c.id = b64urlToBuffer(c.id);
            });

            const credential = await navigator.credentials.create({ publicKey: options });

            const body = {
                id:    credential.id,
                rawId: bufferToB64url(credential.rawId),
                type:  credential.type,
                response: {
                    attestationObject: bufferToB64url(credential.response.attestationObject),
                    clientDataJSON:    bufferToB64url(credential.response.clientDataJSON),
                },
            };

            const completeResp = await fetch(WEBAUTHN_REGISTER_COMPLETE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify(body),
            });

            const result = await completeResp.json();
            if (result.status === 'ok') {
                status.textContent = '✓ WebAuthn registered successfully!';
                status.style.color = '#1a7a3c';
            } else {
                status.textContent = '✗ ' + (result.error || 'Registration failed.');
                status.style.color = '#c00';
            }
        } catch (err) {
            status.textContent = err.name === 'NotAllowedError'
                ? 'Registration cancelled.'
                : 'Error: ' + err.message;
            status.style.color = '#c00';
        }
    });

});